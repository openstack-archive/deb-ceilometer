#
# Copyright 2013 eNovance
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

from oslo_context import context as req_context
from stevedore import extension

from ceilometer.i18n import _
from ceilometer.openstack.common import log as logging
from ceilometer import pipeline
from ceilometer import transformer


LOG = logging.getLogger(__name__)


_notification_manager = None
_pipeline_manager = None


def _load_notification_manager():
    global _notification_manager, _pipeline_manager

    namespace = 'ceilometer.notification'

    LOG.debug(_('loading notification handlers from %s'), namespace)

    _notification_manager = extension.ExtensionManager(
        namespace=namespace,
        invoke_on_load=True,
        invoke_args=(_pipeline_manager, )
    )

    if not list(_notification_manager):
        LOG.warning(_('Failed to load any notification handlers for %s'),
                    namespace)


def _load_pipeline_manager():
    global _pipeline_manager

    _pipeline_manager = pipeline.setup_pipeline(
        transformer.TransformerExtensionManager(
            'ceilometer.transformer',
        ),
    )


def notify(context, message):
    """Sends a notification as a meter using Ceilometer pipelines."""
    if not _pipeline_manager:
        _load_pipeline_manager()
    if not _notification_manager:
        _load_notification_manager()
    _notification_manager.map_method(
        'to_samples_and_publish',
        context=context or req_context.get_admin_context(),
        notification=message)
