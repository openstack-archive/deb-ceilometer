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

"""
SQLAlchemy models for Ceilometer data.
"""
import hashlib
import json

from oslo_utils import timeutils
import six
from sqlalchemy import (Column, Integer, String, ForeignKey, Index,
                        UniqueConstraint, BigInteger)
from sqlalchemy import event, select
from sqlalchemy import Float, Boolean, Text, DateTime
from sqlalchemy.dialects.mysql import DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import deferred
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from ceilometer import utils


class JSONEncodedDict(TypeDecorator):
    """Represents an immutable structure as a json-encoded string."""

    impl = String

    @staticmethod
    def process_bind_param(value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    @staticmethod
    def process_result_value(value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class PreciseTimestamp(TypeDecorator):
    """Represents a timestamp precise to the microsecond."""

    impl = DateTime

    def load_dialect_impl(self, dialect):
        if dialect.name == 'mysql':
            return dialect.type_descriptor(DECIMAL(precision=20,
                                                   scale=6,
                                                   asdecimal=True))
        return self.impl

    @staticmethod
    def process_bind_param(value, dialect):
        if value is None:
            return value
        elif dialect.name == 'mysql':
            return utils.dt_to_decimal(value)
        return value

    @staticmethod
    def process_result_value(value, dialect):
        if value is None:
            return value
        elif dialect.name == 'mysql':
            return utils.decimal_to_dt(value)
        return value


class CeilometerBase(object):
    """Base class for Ceilometer Models."""
    __table_args__ = {'mysql_charset': "utf8",
                      'mysql_engine': "InnoDB"}
    __table_initialized__ = False

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def update(self, values):
        """Make the model object behave like a dict."""
        for k, v in six.iteritems(values):
            setattr(self, k, v)


Base = declarative_base(cls=CeilometerBase)


class MetaText(Base):
    """Metering text metadata."""

    __tablename__ = 'metadata_text'
    __table_args__ = (
        Index('ix_meta_text_key', 'meta_key'),
    )
    id = Column(Integer, ForeignKey('resource.internal_id'), primary_key=True)
    meta_key = Column(String(255), primary_key=True)
    value = Column(Text)


class MetaBool(Base):
    """Metering boolean metadata."""

    __tablename__ = 'metadata_bool'
    __table_args__ = (
        Index('ix_meta_bool_key', 'meta_key'),
    )
    id = Column(Integer, ForeignKey('resource.internal_id'), primary_key=True)
    meta_key = Column(String(255), primary_key=True)
    value = Column(Boolean)


class MetaBigInt(Base):
    """Metering integer metadata."""

    __tablename__ = 'metadata_int'
    __table_args__ = (
        Index('ix_meta_int_key', 'meta_key'),
    )
    id = Column(Integer, ForeignKey('resource.internal_id'), primary_key=True)
    meta_key = Column(String(255), primary_key=True)
    value = Column(BigInteger, default=False)


class MetaFloat(Base):
    """Metering float metadata."""

    __tablename__ = 'metadata_float'
    __table_args__ = (
        Index('ix_meta_float_key', 'meta_key'),
    )
    id = Column(Integer, ForeignKey('resource.internal_id'), primary_key=True)
    meta_key = Column(String(255), primary_key=True)
    value = Column(Float(53), default=False)


class Meter(Base):
    """Meter definition data."""

    __tablename__ = 'meter'
    __table_args__ = (
        UniqueConstraint('name', 'type', 'unit', name='def_unique'),
        Index('ix_meter_name', 'name'),
    )
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(String(255))
    unit = Column(String(255))
    samples = relationship("Sample", backref="meter")


class Resource(Base):
    """Resource data."""

    __tablename__ = 'resource'
    __table_args__ = (
        # TODO(gordc): this should exist but the attribute values we set
        #              for user/project/source/resource id's are too large
        #              for a uuid.
        # UniqueConstraint('resource_id', 'user_id', 'project_id',
        #                  'source_id', 'metadata_hash',
        #                  name='res_def_unique'),
        Index('ix_resource_resource_id', 'resource_id'),
        Index('ix_resource_metadata_hash', 'metadata_hash'),
    )

    internal_id = Column(Integer, primary_key=True)
    user_id = Column(String(255))
    project_id = Column(String(255))
    source_id = Column(String(255))
    resource_id = Column(String(255), nullable=False)
    resource_metadata = deferred(Column(JSONEncodedDict()))
    metadata_hash = deferred(Column(String(32)))
    samples = relationship("Sample", backref="resource")
    meta_text = relationship("MetaText", backref="resource",
                             cascade="all, delete-orphan")
    meta_float = relationship("MetaFloat", backref="resource",
                              cascade="all, delete-orphan")
    meta_int = relationship("MetaBigInt", backref="resource",
                            cascade="all, delete-orphan")
    meta_bool = relationship("MetaBool", backref="resource",
                             cascade="all, delete-orphan")


@event.listens_for(Resource, "before_insert")
def before_insert(mapper, connection, target):
    metadata = json.dumps(target.resource_metadata, sort_keys=True)
    target.metadata_hash = hashlib.md5(metadata).hexdigest()


class Sample(Base):
    """Metering data."""

    __tablename__ = 'sample'
    __table_args__ = (
        Index('ix_sample_timestamp', 'timestamp'),
        Index('ix_sample_resource_id', 'resource_id'),
        Index('ix_sample_meter_id', 'meter_id'),
        Index('ix_sample_meter_id_resource_id', 'meter_id', 'resource_id')
    )
    id = Column(Integer, primary_key=True)
    meter_id = Column(Integer, ForeignKey('meter.id'))
    resource_id = Column(Integer, ForeignKey('resource.internal_id'))
    volume = Column(Float(53))
    timestamp = Column(PreciseTimestamp(), default=lambda: timeutils.utcnow())
    recorded_at = Column(PreciseTimestamp(),
                         default=lambda: timeutils.utcnow())
    message_signature = Column(String(64))
    message_id = Column(String(128))


class FullSample(Base):
    """Mapper model.

    It's needed as many of the filters work against raw data which is split
    between Meter, Sample, and Resource tables
    """
    meter = Meter.__table__
    sample = Sample.__table__
    resource = Resource.__table__
    __table__ = (select([sample.c.id, meter.c.name.label('counter_name'),
                         meter.c.type.label('counter_type'),
                         meter.c.unit.label('counter_unit'),
                         sample.c.volume.label('counter_volume'),
                         resource.c.resource_id, resource.c.source_id,
                         resource.c.user_id, resource.c.project_id,
                         resource.c.resource_metadata, resource.c.internal_id,
                         sample.c.timestamp, sample.c.message_id,
                         sample.c.message_signature, sample.c.recorded_at])
                 .select_from(
                     sample.join(meter, sample.c.meter_id == meter.c.id).join(
                         resource,
                         sample.c.resource_id == resource.c.internal_id))
                 .alias())


class Alarm(Base):
    """Define Alarm data."""
    __tablename__ = 'alarm'
    __table_args__ = (
        Index('ix_alarm_user_id', 'user_id'),
        Index('ix_alarm_project_id', 'project_id'),
    )
    alarm_id = Column(String(128), primary_key=True)
    enabled = Column(Boolean)
    name = Column(Text)
    type = Column(String(50))
    severity = Column(String(50))
    description = Column(Text)
    timestamp = Column(PreciseTimestamp, default=lambda: timeutils.utcnow())

    user_id = Column(String(255))
    project_id = Column(String(255))

    state = Column(String(255))
    state_timestamp = Column(PreciseTimestamp,
                             default=lambda: timeutils.utcnow())

    ok_actions = Column(JSONEncodedDict)
    alarm_actions = Column(JSONEncodedDict)
    insufficient_data_actions = Column(JSONEncodedDict)
    repeat_actions = Column(Boolean)

    rule = Column(JSONEncodedDict)
    time_constraints = Column(JSONEncodedDict)


class AlarmChange(Base):
    """Define AlarmChange data."""
    __tablename__ = 'alarm_history'
    __table_args__ = (
        Index('ix_alarm_history_alarm_id', 'alarm_id'),
    )
    event_id = Column(String(128), primary_key=True)
    alarm_id = Column(String(128))
    on_behalf_of = Column(String(255))
    project_id = Column(String(255))
    user_id = Column(String(255))
    type = Column(String(20))
    detail = Column(Text)
    timestamp = Column(PreciseTimestamp, default=lambda: timeutils.utcnow())


class EventType(Base):
    """Types of event records."""
    __tablename__ = 'event_type'

    id = Column(Integer, primary_key=True)
    desc = Column(String(255), unique=True)

    def __init__(self, event_type):
        self.desc = event_type

    def __repr__(self):
        return "<EventType: %s>" % self.desc


class Event(Base):
    __tablename__ = 'event'
    __table_args__ = (
        Index('ix_event_message_id', 'message_id'),
        Index('ix_event_type_id', 'event_type_id'),
        Index('ix_event_generated', 'generated')
    )
    id = Column(Integer, primary_key=True)
    message_id = Column(String(50), unique=True)
    generated = Column(PreciseTimestamp())
    raw = deferred(Column(JSONEncodedDict()))

    event_type_id = Column(Integer, ForeignKey('event_type.id'))
    event_type = relationship("EventType", backref='events')

    def __init__(self, message_id, event_type, generated, raw):
        self.message_id = message_id
        self.event_type = event_type
        self.generated = generated
        self.raw = raw

    def __repr__(self):
        return "<Event %d('Event: %s %s, Generated: %s')>" % (self.id,
                                                              self.message_id,
                                                              self.event_type,
                                                              self.generated)


class TraitText(Base):
    """Event text traits."""

    __tablename__ = 'trait_text'
    __table_args__ = (
        Index('ix_trait_text_event_id_key', 'event_id', 'key'),
    )
    event_id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(String(255))


class TraitInt(Base):
    """Event integer traits."""

    __tablename__ = 'trait_int'
    __table_args__ = (
        Index('ix_trait_int_event_id_key', 'event_id', 'key'),
    )
    event_id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Integer)


class TraitFloat(Base):
    """Event float traits."""

    __tablename__ = 'trait_float'
    __table_args__ = (
        Index('ix_trait_float_event_id_key', 'event_id', 'key'),
    )
    event_id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Float(53))


class TraitDatetime(Base):
    """Event datetime traits."""

    __tablename__ = 'trait_datetime'
    __table_args__ = (
        Index('ix_trait_datetime_event_id_key', 'event_id', 'key'),
    )
    event_id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(PreciseTimestamp())
