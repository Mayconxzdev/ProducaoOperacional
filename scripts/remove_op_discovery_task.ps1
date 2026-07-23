$ErrorActionPreference = "SilentlyContinue"
Unregister-ScheduledTask -TaskName "ProducaoOperacional-ImportarNovasOPs" -Confirm:$false
