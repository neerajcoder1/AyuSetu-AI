"""
services/redflag Entry Point
============================
Microservice root for Red-Flag Engine (Port 8105).
"""

from ayusetu.redflag.app import redflag_app

app = redflag_app
