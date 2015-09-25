#!/bin/bash -xe

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# This script is executed inside post_test_hook function in devstack gate.

function generate_testr_results {
    if [ -f .testrepository/0 ]; then
        sudo .tox/functional/bin/testr last --subunit > $WORKSPACE/testrepository.subunit
        sudo mv $WORKSPACE/testrepository.subunit $BASE/logs/testrepository.subunit
        sudo /usr/os-testr-env/bin/subunit2html $BASE/logs/testrepository.subunit $BASE/logs/testr_results.html
        sudo gzip -9 $BASE/logs/testrepository.subunit
        sudo gzip -9 $BASE/logs/testr_results.html
        sudo chown jenkins:jenkins $BASE/logs/testrepository.subunit.gz $BASE/logs/testr_results.html.gz
        sudo chmod a+r $BASE/logs/testrepository.subunit.gz $BASE/logs/testr_results.html.gz
    fi
}

# If we're running in the gate find our keystone endpoint to give to
# gabbi tests and do a chown. Otherwise the existing environment
# should provide URL and TOKEN.
if [ -d $BASE/new/devstack ]; then
    export CEILOMETER_DIR="$BASE/new/ceilometer"
    STACK_USER=stack
    sudo chown -R $STACK_USER:stack $CEILOMETER_DIR
    source $BASE/new/devstack/openrc admin admin
    # Go to the ceilometer dir
    cd $CEILOMETER_DIR
fi

openstack catalog list
export AODH_SERVICE_URL=$(openstack catalog show alarming -c endpoints -f value | awk '/publicURL/{print $2}')
export GNOCCHI_SERVICE_URL=$(openstack catalog show metric -c endpoints -f value | awk '/publicURL/{print $2}')
export HEAT_SERVICE_URL=$(openstack catalog show orchestration -c endpoints -f value | awk '/publicURL/{print $2}')
export NOVA_SERVICE_URL=$(openstack catalog show compute -c endpoints -f value | awk '/publicURL/{print $2}')
export GLANCE_IMAGE_NAME=$(openstack image list | awk '/ cirros.*uec /{print $4}')
export ADMIN_TOKEN=$(openstack token issue -c id -f value)

# Run tests
echo "Running telemetry integration test suite"
set +e

sudo -E -H -u ${STACK_USER:-${USER}} tox -eintegration
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ] ; then
    set +x
    echo "* Heat stack:"
    heat stack-show integration_test
    echo "* Alarm list:"
    ceilometer alarm-list
    echo "* Nova instance list:"
    openstack server list

    # TODO(sileht): replace by gnocchiclient when available
    echo "* Gnocchi instance list:"
    curl -s -X GET -H 'Content-Type: application/json' -H "X-Auth-Token: $ADMIN_TOKEN" $GNOCCHI_SERVICE_URL/v1/resource/instance | python -m "json.tool"
    for instance_id in $(openstack server list -f value -c ID); do
        echo "* Nova instance detail:"
        openstack server show $instance_id

        echo "* Gnocchi measures for instance ${instance_id}:"
        output=$(curl -s -X GET -H 'Content-Type: application/json' -H "X-Auth-Token: $ADMIN_TOKEN" $GNOCCHI_SERVICE_URL/v1/resource/instance/$instance_id/metric/cpu_util/measures)
        echo $output | python -m "json.tool" || echo -e "\n$output"
    done

    echo "* Unprocessed measures:"
    find $GNOCCHI_DATA_DIR/measures
    set -x
fi

set -e

# Collect and parse result
if [ -n "$CEILOMETER_DIR" ]; then
    generate_testr_results
fi
exit $EXIT_CODE
