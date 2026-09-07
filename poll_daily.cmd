@echo off
rem OpportunityRadar M3 daily publish poll (scheduled task: daily 09:10)
cd /d "%~dp0"
"C:\Users\30689\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m radar.publish.audit_gate --poll >> data\publish_poll.log 2>&1
