from datetime import timedelta

from app.logic import get_now


def seed() -> dict:
    now = get_now()

    def ago(h):
        return now - timedelta(hours=h)

    def mk(sid, carrier, origin, dest, lane_type, status, picked_h, scan_h, loc, **kw):
        base = {
            "shipment_id": sid, "order_id": "ORD-" + sid.split("-")[1], "carrier": carrier,
            "origin": origin, "destination": dest, "lane_type": lane_type, "status": status,
            "picked_up_at": ago(picked_h), "last_scan_at": ago(scan_h), "last_scan_location": loc,
            "delivery_attempts": 0, "failure_reason": None, "damage_reported": False,
            "delivered_at": None, "address_updates": 0, "refunded_inr": 0, "log": [],
        }
        base.update(kw)
        return base

    ships = [
        mk("SHP-1001", "ExpressOne", "Bengaluru", "Mumbai", "metro", "IN_TRANSIT", 54, 6, "Pune Hub"),
        mk("SHP-1002", "RoadRunner Logistics", "Hyderabad", "Nagpur", "non_metro", "IN_TRANSIT", 110, 80, "Adilabad Hub"),
        mk("SHP-1003", "SwiftPost", "Pune", "Delhi", "metro", "DELIVERY_FAILED", 50, 4, "Delhi Depot",
           delivery_attempts=1, failure_reason="ADDRESS_INCOMPLETE"),
        mk("SHP-1004", "ExpressOne", "Delhi", "Gurugram", "metro", "DELIVERED", 70, 20, "Gurugram",
           damage_reported=True, delivered_at=ago(20)),
        mk("SHP-1005", "ExpressOne", "Bengaluru", "Mumbai", "metro", "IN_TRANSIT", 10, 2, "Bengaluru Hub"),
        mk("SHP-1006", "ExpressOne", "Mumbai", "Nashik", "non_metro", "IN_TRANSIT", 58, 5, "Thane Hub"),
        mk("SHP-1007", "RoadRunner Logistics", "Chennai", "Madurai", "non_metro", "IN_TRANSIT", 150, 100, "Trichy Hub"),
        mk("SHP-1008", "RoadRunner Logistics", "Chennai", "Madurai", "non_metro", "IN_TRANSIT", 120, 60, "Trichy Hub"),
        mk("SHP-1009", "RoadRunner Logistics", "Chennai", "Madurai", "non_metro", "IN_TRANSIT", 110, 55, "Trichy Hub"),
        mk("SHP-1010", "SwiftPost", "Kolkata", "Patna", "non_metro", "DELIVERY_FAILED", 140, 10, "Patna Depot",
           delivery_attempts=3, failure_reason="CUSTOMER_UNREACHABLE"),
        mk("SHP-1011", "SwiftPost", "Kolkata", "Ranchi", "non_metro", "RETURNED_TO_ORIGIN", 200, 5, "Kolkata Hub",
           delivery_attempts=3, failure_reason="CUSTOMER_UNREACHABLE"),
    ]
    values = {"1001": (1200, "sku-A"), "1002": (1800, "sku-B"), "1003": (900, "sku-A"), "1004": (7500, "sku-A"),
              "1005": (600, "sku-A"), "1006": (2400, "sku-A"), "1007": (3500, "sku-A"), "1008": (4200, "sku-A"),
              "1009": (15000, "sku-A"), "1010": (1500, "sku-A"), "1011": (2500, "sku-A")}
    orders = {
        f"ORD-{n}": {"order_id": f"ORD-{n}", "sku": sku, "value_inr": val, "customer_email": f"customer{n}@example.com"}
        for n, (val, sku) in values.items()
    }
    return {
        "shipments": {s["shipment_id"]: s for s in ships},
        "orders": orders,
        "inventory": {"sku-A": 5, "sku-B": 0},
    }