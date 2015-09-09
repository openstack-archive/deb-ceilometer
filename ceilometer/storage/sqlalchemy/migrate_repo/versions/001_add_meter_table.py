# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import UniqueConstraint


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)

    meter = Table(
        'meter', meta,
        Column('id', Integer, primary_key=True, index=True),
        Column('counter_name', String(255)),
        Column('user_id', String(255), index=True),
        Column('project_id', String(255), index=True),
        Column('resource_id', String(255)),
        Column('resource_metadata', String(5000)),
        Column('counter_type', String(255)),
        Column('counter_volume', Integer),
        Column('counter_duration', Integer),
        Column('timestamp', DateTime(timezone=False), index=True),
        Column('message_signature', String(1000)),
        Column('message_id', String(1000)),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    resource = Table(
        'resource', meta,
        Column('id', String(255), primary_key=True, index=True),
        Column('resource_metadata', String(5000)),
        Column('project_id', String(255), index=True),
        Column('received_timestamp', DateTime(timezone=False)),
        Column('timestamp', DateTime(timezone=False), index=True),
        Column('user_id', String(255), index=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    user = Table(
        'user', meta,
        Column('id', String(255), primary_key=True, index=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    project = Table(
        'project', meta,
        Column('id', String(255), primary_key=True, index=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    sourceassoc = Table(
        'sourceassoc', meta,
        Column('source_id', String(255), index=True),
        Column('user_id', String(255)),
        Column('project_id', String(255)),
        Column('resource_id', String(255)),
        Column('meter_id', Integer),
        Index('idx_su', 'source_id', 'user_id'),
        Index('idx_sp', 'source_id', 'project_id'),
        Index('idx_sr', 'source_id', 'resource_id'),
        Index('idx_sm', 'source_id', 'meter_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    source = Table(
        'source', meta,
        Column('id', String(255), primary_key=True, index=True),
        UniqueConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    tables = [meter, project, resource, user, source, sourceassoc]
    for i in sorted(tables, key=lambda table: table.fullname):
        i.create()
