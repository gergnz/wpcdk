import os
from constructs import Construct
from aws_cdk import Stack, RemovalPolicy, CfnOutput
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_iam as iam

class WpcdkStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:

        # default is to use graviton CPUs
        machine_image = ec2.MachineImage.latest_amazon_linux(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
                cpu_type=ec2.AmazonLinuxCpuType('ARM_64')
            )

        app_instance_type = ec2.InstanceType.of(
                ec2.InstanceClass.COMPUTE6_GRAVITON2,
                ec2.InstanceSize.LARGE,
            )

        db_instance_type = ec2.InstanceType.of(
                ec2.InstanceClass.MEMORY6_GRAVITON,
                ec2.InstanceSize.LARGE,
            )

        if 'APPCPU' in os.environ:
            if os.environ.get('APPCPU') == 'INTEL':
                machine_image = ec2.MachineImage.latest_amazon_linux(
                        generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
                        cpu_type=ec2.AmazonLinuxCpuType('X86_64')
                    )

                app_instance_type = ec2.InstanceType.of(
                        ec2.InstanceClass.COMPUTE5,
                        ec2.InstanceSize.LARGE,
                    )
            if os.environ.get('APPCPU') == 'AMD':
                machine_image = ec2.MachineImage.latest_amazon_linux(
                        generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
                        cpu_type=ec2.AmazonLinuxCpuType('X86_64')
                    )

                app_instance_type = ec2.InstanceType.of(
                        ec2.InstanceClass.COMPUTE5_AMD,
                        ec2.InstanceSize.LARGE,
                    )

        if 'DBCPU' in os.environ:
            if os.environ.get('DBCPU') == 'INTEL':
                db_instance_type = ec2.InstanceType.of(
                        ec2.InstanceClass.MEMORY5,
                        ec2.InstanceSize.LARGE,
                    )
            # sadly there is no AMD RDS instance types

        super().__init__(scope, id, **kwargs)

        vpc = ec2.Vpc(self, "vpc",
                nat_gateways=0
                )

        db = rds.DatabaseInstance(self, "db",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0
            ),
            vpc=vpc,
            availability_zone=vpc.availability_zones[0],
            instance_type=db_instance_type,
            removal_policy=RemovalPolicy.DESTROY,
            vpc_subnets=ec2.SubnetSelection(one_per_az=True, subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            deletion_protection=False
            )

        app = ec2.Instance(self, "app",
            instance_type=app_instance_type,
            machine_image=machine_image,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(one_per_az=True, subnet_type=ec2.SubnetType.PUBLIC),
            availability_zone=vpc.availability_zones[0],
            key_name="gjc",
            user_data_causes_replacement=True
                )

        cfn_app = app.node.default_child

        cfn_app.monitoring = True

        db.connections.allow_from(app, ec2.Port.tcp(3306))
        app.connections.allow_from_any_ipv4(ec2.Port.tcp(22))
        app.connections.allow_from_any_ipv4(ec2.Port.tcp(80))
        app.role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'))
        app.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db.secret.secret_full_arn]
                    )
                )

        app.add_user_data('''
region=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone | sed 's/[a-z]$//')
aws --region $region secretsmanager get-secret-value --secret-id '''+db.secret.secret_full_arn+''' >> /tmp/details
yum install -y jq httpd mariadb
amazon-linux-extras install -y php7.2
systemctl enable httpd
systemctl start httpd
cd /tmp; wget https://wordpress.org/latest.zip
cd /var/www/html
unzip /tmp/latest.zip
echo "<?php" > wordpress/wp-config.php
echo "define( 'DB_NAME', 'wordpress' );" >> wordpress/wp-config.php
echo "define( 'DB_USER', '$(cat /tmp/details | jq -r '.SecretString' | jq -r '.username')' );" >> wordpress/wp-config.php
echo "define( 'DB_PASSWORD', '$(cat /tmp/details | jq -r '.SecretString' | jq -r '.password')' );" >> wordpress/wp-config.php
echo "define( 'DB_HOST', '$(cat /tmp/details | jq -r '.SecretString' | jq -r '.host')' );" >> wordpress/wp-config.php
echo "define( 'DB_CHARSET', 'utf8' );" >> wordpress/wp-config.php
echo "define( 'DB_COLLATE', '' );" >> wordpress/wp-config.php
curl -s https://api.wordpress.org/secret-key/1.1/salt/ >> wordpress/wp-config.php
echo "\$table_prefix = 'wp_';" >> wordpress/wp-config.php
echo "define( 'WP_DEBUG', false );" >> wordpress/wp-config.php
echo "if ( ! defined( 'ABSPATH' ) ) {" >> wordpress/wp-config.php
echo "        define( 'ABSPATH', __DIR__ . '/' );" >> wordpress/wp-config.php
echo "}" >> wordpress/wp-config.php
echo "require_once ABSPATH . 'wp-settings.php';" >> wordpress/wp-config.php
echo "create database wordpress;" | mysql -h$(cat /tmp/details | jq -r '.SecretString' | jq -r '.host') -u$(cat /tmp/details | jq -r '.SecretString' | jq -r '.username') -p$(cat /tmp/details| jq -r '.SecretString' | jq -r '.password')
curl "http://$(curl http://ipv4.icanhazip.com)/wordpress/wp-admin/install.php?step=2" --data-raw 'weblog_title=Wordpress&user_name=admin&admin_password=oKdy7%212cVumXZLzW8%29&admin_password2=oKdy7%212cVumXZLzW8%29&admin_email=admin%40example.com&blog_public=0&Submit=Install+WordPress&language='
'''
        )
# oKdy7!2cVumXZLzW8)

        CfnOutput(self, "output",
                description="URL",
                value="http://"+app.instance_public_ip+"/wordpress/"
                )
