# -*- encoding: utf-8 -*-
#
# Author: Guillaume Pernot <gpernot@praksys.org>
#
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

from sqlalchemy import *

meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    meter = Table('meter', meta, autoload=True)
    unit = Column('counter_unit', String(255))
    meter.create_column(unit)


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    meter = Table('meter', meta, autoload=True)
    unit = Column('counter_unit', String(255))
    meter.drop_column(unit)
