#!/usr/bin/env python3

from aws_cdk import core

from wpcdk.wpcdk_stack import WpcdkStack


app = core.App()
WpcdkStack(app, "wpcdk")

app.synth()
