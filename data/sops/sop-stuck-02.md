---
id: sop-stuck-02
title: Shipment With No Scan Update
version: 2
---
# Shipment With No Scan Update
## Scope
Applies when the last carrier scan is older than 48 hours and the shipment has not been delivered.
## Diagnosis steps
1. Confirm the last scan timestamp and the facility where it occurred.
2. Rule out weekend or public holiday exclusions in the carrier SLA.
3. Check whether other shipments on the same lane also show no scans, which suggests a hub issue rather than a single lost parcel.
## Actions by silence
No scan for 48 to 72 hours: request a trace from the carrier and notify the customer.
No scan for 72 to 96 hours: open a lost-shipment investigation and place a hold on any refund.
No scan for over 96 hours: mark the shipment as presumed lost and propose a reship or refund, subject to approval.