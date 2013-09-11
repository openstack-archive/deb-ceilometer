..
      Copyright 2012 New Dream Network (DreamHost)
      Copyright 2013 eNovance

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

==========
 Glossary
==========

.. glossary::

   agent
     Software service running on the OpenStack infrastructure
     measuring usage and sending the results to the :term:`collector`.

   alarm
     An action triggered whenever a meter reaches a certain threshold.

   API server
     HTTP REST API service for ceilometer.

   ceilometer
     From Wikipedia [#]_:

       A ceilometer is a device that uses a laser or other light
       source to determine the height of a cloud base.

   central agent
     Software service running on a central management node within the
     OpenStack infrastructure measuring usage and sending the results
     to the :term:`collector`.

   collector
     Software service running on the OpenStack infrastructure
     monitoring notifications from other OpenStack components and
     samples from the ceilometer agent and recording the results
     in the database.

   compute agent
     Software service running on a compute node within the OpenStack
     infrastructure measuring usage and sending the results to the
     :term:`collector`.

   data store
     Storage system for recording data collected by ceilometer.

   meter
     The measurements tracked for a resource. For example, an instance has
     a number of meters, such as duration of instance, CPU time used,
     number of disk io requests, etc.
     Three types of meters are defined in ceilometer:
      * Cumulative: Increasing over time (e.g. disk I/O)
      * Gauge: Discrete items (e.g. floating IPs, image uploads) and fluctuating
        values (e.g. number of Swift objects)
      * Delta: Incremental change to a counter over time (e.g. bandwidth delta)

   notification
      A message sent via an external OpenStack system (e.g Nova, Glance,
      etc) using the Oslo notification mechanism [#]_. These notifications
      are usually sent to and received by Ceilometer through the notifier
      RPC driver.

   non-repudiable
    From Wikipedia [#]_:

      Non-repudiation refers to a state of affairs where the purported
      maker of a statement will not be able to successfully challenge
      the validity of the statement or contract. The term is often
      seen in a legal setting wherein the authenticity of a signature
      is being challenged. In such an instance, the authenticity is
      being "repudiated".

   project
     The OpenStack tenant or project.

   resource
     The OpenStack entity being metered (e.g. instance, volume, image, etc).

   sample
     Data sample for a particular meter.

   source
     The origin of metering data. This field is set to "openstack" by default.
     It can be configured to a different value using the sample_source field
     in the ceilometer.conf file.

   user
     An OpenStack user.

.. [#] http://en.wikipedia.org/wiki/Ceilometer
.. [#] https://git.openstack.org/cgit/openstack/ceilometer/tree/ceilometer/openstack/common/notifier
.. [#] http://en.wikipedia.org/wiki/Non-repudiation
