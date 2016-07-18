Enable Compute service meters for Red Hat Enterprise Linux and CentOS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Telemetry uses a combination of notifications and an agent to collect
Compute meters. Perform these steps on each compute node.

Install and configure components
--------------------------------

#. Install the packages:

   .. code-block:: console

      # yum install openstack-ceilometer-compute python-ceilometerclient python-pecan

.. include:: install-nova-common.rst

Finalize installation
---------------------

#. Start the agent and configure it to start when the system boots:

   .. code-block:: console

      # systemctl enable openstack-ceilometer-compute.service
      # systemctl start openstack-ceilometer-compute.service

#. Restart the Compute service:

   .. code-block:: console

      # systemctl restart openstack-nova-compute.service
