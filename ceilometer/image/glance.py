#
# Copyright 2012 New Dream Network, LLC (DreamHost)
#
# Author: Julien Danjou <julien@danjou.info>
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
"""Common code for working with images
"""

from __future__ import absolute_import
import itertools

import glanceclient
from oslo.config import cfg
from oslo.utils import timeutils

from ceilometer.central import plugin
from ceilometer import sample


OPTS = [
    cfg.IntOpt('glance_page_size',
               default=0,
               help="Number of items to request in "
                    "each paginated Glance API request "
                    "(parameter used by glancecelient). "
                    "If this is less than or equal to 0, "
                    "page size is not specified "
                    "(default value in glanceclient is used)."),
]

service_types_opts = [
    cfg.StrOpt('glance',
               default='image',
               help='Glance service type.'),
]

cfg.CONF.register_opts(OPTS)
cfg.CONF.register_opts(service_types_opts, group='service_types')


class _Base(plugin.CentralPollster):

    @property
    def default_discovery(self):
        return 'endpoint:%s' % cfg.CONF.service_types.glance

    @staticmethod
    def get_glance_client(ksclient, endpoint):
        # hard-code v1 glance API version selection while v2 API matures
        service_credentials = cfg.CONF.service_credentials
        return glanceclient.Client('1', endpoint,
                                   token=ksclient.auth_token,
                                   cacert=service_credentials.os_cacert,
                                   insecure=service_credentials.insecure,
                                   timeout=cfg.CONF.http_timeout)

    def _get_images(self, ksclient, endpoint):
        client = self.get_glance_client(ksclient, endpoint)
        page_size = cfg.CONF.glance_page_size
        kwargs = {}
        if page_size > 0:
            kwargs['page_size'] = page_size
        rawImageList = list(itertools.chain(
            client.images.list(filters={"is_public": True}, **kwargs),
            # TODO(eglynn): extend glance API with all_tenants logic to
            #              avoid second call to retrieve private images
            client.images.list(filters={"is_public": False}, **kwargs)))

        # When retrieving images from glance, glance will check
        # whether the user is of 'admin_role' which is
        # configured in glance-api.conf. If the user is of
        # admin_role, and is querying public images(which means
        # that the 'is_public' param is set to be True),
        # glance will ignore 'is_public' parameter and returns
        # all the public images together with private images.
        # As a result, if the user/tenant has an admin role
        # for ceilometer to collect image list,
        # the _Base.iter_images method will return an image list
        # which contains duplicate images. Add the following
        # code to avoid recording down duplicate image events.
        imageIdSet = set(image.id for image in rawImageList)

        for image in rawImageList:
            if image.id in imageIdSet:
                imageIdSet -= set([image.id])
                yield image

    def _iter_images(self, ksclient, cache, endpoint):
        """Iterate over all images."""
        key = '%s-images' % endpoint
        if key not in cache:
            cache[key] = list(self._get_images(ksclient, endpoint))
        return iter(cache[key])

    @staticmethod
    def extract_image_metadata(image):
        return dict((k, getattr(image, k))
                    for k in
                    [
                        "status",
                        "is_public",
                        "name",
                        "deleted",
                        "container_format",
                        "created_at",
                        "disk_format",
                        "updated_at",
                        "properties",
                        "min_disk",
                        "protected",
                        "checksum",
                        "deleted_at",
                        "min_ram",
                        "size", ])


class ImagePollster(_Base):
    def get_samples(self, manager, cache, resources):
        for endpoint in resources:
            for image in self._iter_images(manager.keystone, cache, endpoint):
                yield sample.Sample(
                    name='image',
                    type=sample.TYPE_GAUGE,
                    unit='image',
                    volume=1,
                    user_id=None,
                    project_id=image.owner,
                    resource_id=image.id,
                    timestamp=timeutils.isotime(),
                    resource_metadata=self.extract_image_metadata(image),
                )


class ImageSizePollster(_Base):
    def get_samples(self, manager, cache, resources):
        for endpoint in resources:
            for image in self._iter_images(manager.keystone, cache, endpoint):
                yield sample.Sample(
                    name='image.size',
                    type=sample.TYPE_GAUGE,
                    unit='B',
                    volume=image.size,
                    user_id=None,
                    project_id=image.owner,
                    resource_id=image.id,
                    timestamp=timeutils.isotime(),
                    resource_metadata=self.extract_image_metadata(image),
                )
