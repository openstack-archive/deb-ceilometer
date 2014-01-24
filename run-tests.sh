#!/bin/bash
set -e

function clean_exit(){
    local error_code="$?"
    rm -rf ${MONGO_DATA}
    if [ "$MONGO_PID" ]; then
        kill -9 ${MONGO_PID} || true
    fi
    return $error_code
}

if [ "$1" = "--coverage" ]; then
	COVERAGE_ARG="$1"
	shift
fi

if [ ! "$COVERAGE_ARGS" ]; then
	# Nova notifier tests
	bash tools/init_testr_if_needed.sh
	python setup.py testr --slowest --testr-args="--here=nova_tests $*"
fi

# Main unit tests
MONGO_DATA=`mktemp -d /tmp/CEILO-MONGODB-XXXXX`
MONGO_PORT=29000
trap "clean_exit" EXIT
mkfifo ${MONGO_DATA}/out
export PATH=${PATH:+$PATH:}/sbin:/usr/sbin
if ! which mongod >/dev/null 2>&1
then
    echo "Could not find mongod command" 1>&2
    exit 1
fi
mongod --maxConns 32 --nojournal --noprealloc --smallfiles --quiet --noauth --port ${MONGO_PORT} --dbpath "${MONGO_DATA}" --bind_ip localhost --config /dev/null &>${MONGO_DATA}/out &
MONGO_PID=$!
# Wait for Mongo to start listening to connections
while read line
do
    echo "$line" | grep -q "waiting for connections on port ${MONGO_PORT}" && break
done < ${MONGO_DATA}/out
# Read the fifo for ever otherwise mongod would block
# + that gives us the log on screen
cat ${MONGO_DATA}/out > /dev/null &
export CEILOMETER_TEST_MONGODB_URL="mongodb://localhost:${MONGO_PORT}/ceilometer"
python setup.py testr --slowest --testr-args="$*" $COVERAGE_ARG
