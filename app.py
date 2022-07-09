#!/usr/bin/env python3

from aws_cdk import App

from wpcdk.wpcdk_stack import WpcdkStack


app = App()
WpcdkStack(app, "wpcdk")

app.synth()
