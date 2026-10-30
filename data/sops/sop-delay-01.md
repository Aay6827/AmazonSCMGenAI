---
id: sop-delay-01
title: Delayed In-Transit Shipment
version: 3
---
# Delayed In-Transit Shipment
## Scope
Applies when a shipment has missed its next expected scan within the carrier SLA window but has had a scan in the last 48 hours.
## Diagnosis steps
1. Fetch shipment status and the last scan location.
2. Compare elapsed time since pickup against the carrier SLA for the lane (see sla-carriers-06).
3. Check for regional disruption flags such as weather, strike or hub congestion.
## Actions by delay
Delay under 24 hours beyond SLA: notify the customer with a revised ETA. No carrier escalation needed.
Delay of 24 to 48 hours beyond SLA: raise a carrier escalation ticket and send a proactive delay notice.
Delay over 48 hours beyond SLA: escalate to the carrier account manager and offer a reship if inventory is available.
## Customer communication
Always include the new ETA, the tracking link and an apology. Do not promise compensation before approval.