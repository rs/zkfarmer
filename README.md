ZooKeeper Farmer
================

ZkFarmer is a set of tools to easily manage distributed server farms using [Apache ZooKeeper](http://zookeeper.apache.org/).

With ZkFarmer, each server registers themself in one or several farms. Thru this registration, they can expose arbitrary information about their status.

On the other end, ZkFarmer helps consumers of the farm to maintain a configuration file in sync with the list of nodes registered in the farm with their respective exposed configuration.

In the middle, ZkFarmer helps monitoring and administrative services to easily change the configuration of each node.

Connecting to Zookeeper
-----------------------

All subcommands of `zkfarmer` needs the full list of you ZooKeeper cluster hosts. You can either pass the list of ZooKeeper hosts via the `ZKHOST` environment variable or via the `--host` parameter. Hosts are host:port pairs separated by comms. All examples in this documentation assumes you have you ZooKeeper hosts configured in your environment.

Joining a Farm
--------------

The `zkfarmer join` command is used on each node to register itself into a farm. The command will create an `ephemeral` node in zookeeper that will live until the program isn't killed. As this command will never return, you should start it as a service using something like `upstart`, `daemontools` or `launchd`.

This command takes two arguments, `farm path` and `conf path`. The `farm path` is the path to an existing znode on the ZooKeeper server used to list all node of a given farm.

The `conf path` is the path to the local configuration to be associated with the node. This configuration can be JSON or PHP file or a DJB like directory configuration. DJB directory is the prefered format for this configuration as it offers better flexibility. With a DJB like directory configuration format, each directory is a dictionary and file a key with contents of the file as value.

Once started, the content of the local configuration is transformed into JSON and stored in an `ephemeral` node in ZooKeeper. The node is named after the IP of the host assigned to the default route.

Lets start the following command from the 1.2.3.4 host:

    zkfarmer join /services/db /var/service/db

Lets assume `/var/service/db` is a directory containing the following structure:

    hostname
    enabled
    mysql/
      replication_delay

The `zkfarmer join` command transformed it to the following JSON object and stored it into `/services/db/1.2.3.4`:

    {
      "hostname": "db-01.example.com",
      "enabled": "0",
      "mysql": {"replication_delay": "0"}
    }

While the `zkfarmer join` command is running, this node will be maintained up to date with local configuration and vis versa. You can `echo 1 > /var/service/db/enabled` from the node, the change will be immediately reflected into the ZooKeeper node JSON content. Any change on the content of node in ZooKeeper will also update the local configuration on the node.

Synced Farm Configuration
-------------------------

On the other end, consumer of the service provided by a farm may not have the ability to keep a permanent connection to zookeeper in order to maintain an up-to-date view of the farm state. ZkFarmer can do this by maintaining a local configuration file. PHP and JSON formats are currently supported, more formats may come in the future.

To do this, use the `zkfarmer export` command. As for the `join` command, it will run forever so you may launch it as a service. While the command is running, the destination configuration file will be synchronized with the content of the farm.

Lets take our previous `/services/db` farm. Running the `zkfarm export /services/db /data/web/conf/database.php` will export and maintain the `/data/web/conf/database.php` file with the follwoing content:

    <?php
    return array
    (
        "1.2.3.4" => array
        (
            "hostname" => "db-01.example.com",
            "enabled" => "0",
            "mysql" => array("replication_delay" => "0"),
        ),
        "1.2.3.5" => array
        (
            "hostname" => "db-02.example.com",
            "enabled" => "0",
            "mysql" => array("replication_delay" => "1"),
        ),
        ...
    );

Additionnaly, you can ask ZkFarmer to execute a command each time the configuration is updated. This command can, for instance, flush some cache, reload the conf in your application etc.

Manage Farms
------------

ZkFarmer comes with some other commands to list, read and write farms content.

### List farms and nodes

The `zkfarm ls` command let you list nodes in ZooKeeper. If the listed node contains ZkFarmer maintained node, you can also list nodes with some of their values:

You can list all the farms you stored in `/services`:

    $ zkfarmer ls /services
    db
    cache
    search
    soft

You can explore the status of nodes in a farm:

    $ zkfarmer ls /services/db --fields enabled,hostname
    1.2.3.4          hostname=db-01.example.com, enabled=0
    1.2.3.5          hostname=db-02.example.com, enabled=1
    ...

To dump sub-fields, use dotted notation (ex: mysql.replication_delay).

### Get field of node

The `zkfarm get` can return the value of a given field of a node:

    $ zkfarmer get /services/db/1.2.3.4 enabled
    0

### Set field of a node

You can also change the field of a node from anywhere on your network:

    $ zkfarmer set /services/db/1.2.3.4 enabled 1
