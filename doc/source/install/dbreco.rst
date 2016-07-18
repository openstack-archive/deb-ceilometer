..
      Copyright 2013 Nicolas Barcet for eNovance

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. _choosing_db_backend:

============================
 Choosing a database backend
============================

.. note::

   Ceilometer's native database capabilities is intended for post processing
   and auditing purposes where responsiveness is not a requirement. It
   captures the full fidelity of each datapoint and thus is not designed
   for low latency use cases. For more responsive use cases, it's recommended
   to store data in an alternative source such as Gnocchi_. Please see
   `Moving from Ceilometer to Gnocchi`_ to find more information.

.. note::

   As of Liberty, alarming support, and subsequently its database, is handled
   by Aodh_.

.. _Aodh: http://docs.openstack.org/developer/aodh/

Selecting a database backend for Ceilometer should not be done lightly for
numerous reasons:

1. Not all backend drivers are equally implemented and tested.  To help you
   make your choice, the table below will give you some idea of the
   status of each of the drivers available in trunk.  Note that we do welcome
   patches to improve completeness and quality of drivers.

2. It may not be a good idea to use the same host as another database as
   Ceilometer can generate a LOT OF WRITES. For this reason it is generally
   recommended, if the deployment is targeting going into production, to use
   a dedicated host, or at least a VM which will be migratable to another
   physical host if needed. The following spreadsheet can help you get an
   idea of the volumes that ceilometer can generate:
   `Google spreadsheet <https://docs.google.com/a/enovance.com/spreadsheet/ccc?key=0AtziNGvs-uPudDhRbEJJOHFXV3d0ZGc1WE9NLTVPX0E#gid=0>`_

3. If you are relying on this backend to bill customers, you will note that
   your capacity to generate revenue is very much linked to its reliability,
   which seems to be a factor dear to many managers.

The following is a table indicating the status of each database drivers:

================== ============================= ===========================================
Driver             API querying                  API statistics
================== ============================= ===========================================
MongoDB            Yes                           Yes
MySQL              Yes                           Yes
PostgreSQL         Yes                           Yes
HBase              Yes                           Yes, except groupby & selectable aggregates
================== ============================= ===========================================


Moving from Ceilometer to Gnocchi
=================================

Gnocchi represents a fundamental change in how data is represented and stored.
Installation and configuration can be found in :ref:`installing_manually`.
Differences between APIs can be found here_.

There currently exists no migration tool between the services. To transition
to Gnocchi, multiple dispatchers can be enabled in the Collector to capture
data in both the native Ceilometer database and Gnocchi. This will allow you
to test Gnocchi and transition to it fully when comfortable. The following
should be included in addition to the required configurations for each
backend::

  [DEFAULT]
  meter_dispatchers=database
  meter_dispatchers=gnocchi

.. _Gnocchi: http://gnocchi.xyz
.. _here: https://docs.google.com/presentation/d/1PefouoeMVd27p2OGDfNQpx18mY-Wk5l0P1Ke2Vt5LwA/edit?usp=sharing
