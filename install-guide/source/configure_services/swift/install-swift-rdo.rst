Enable Object Storage meters for Red Hat Enterprise Linux and CentOS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Telemetry uses a combination of polling and notifications to collect
Object Storage meters.

.. note::

   Your environment must include the Object Storage service.

.. include:: install-swift-prereq-common.rst

Install components
------------------

* Install the packages:

  .. code-block:: console

     # yum install python-ceilometermiddleware

.. include:: install-swift-config-common.rst

Finalize installation
---------------------

* Restart the Object Storage proxy service:

  .. code-block:: console

     # systemctl restart openstack-swift-proxy.service
