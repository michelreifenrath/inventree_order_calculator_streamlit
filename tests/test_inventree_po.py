import sys
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.company import SupplierPart


def main():
    url = "http://10.0.0.33"
    token = "inv-455d26918f7f3e8cdc2ea8c6e1270e72cd02df40-20250408"

    print("Connecting to InvenTree server...")
    api = InvenTreeAPI(url, token=token)

    try:
        parts = Part.list(api, limit=3)
    except Exception as e:
        print(f"Error fetching parts: {e}")
        sys.exit(1)

    if not parts:
        print("No parts found.")
        sys.exit(0)

    for part in parts:
        print(f"\nPart ID: {part.pk}, Name: {part._data.get('name', 'Unnamed')}")

        # Find all supplier parts linked to this part
        try:
            supplier_parts = SupplierPart.list(api, part=part.pk)
        except Exception as e:
            print(f"  Error fetching supplier parts: {e}")
            continue

        if not supplier_parts:
            print("  No supplier parts found for this part.")
            continue

        for sp in supplier_parts:
            print(f"  SupplierPart ID: {sp.pk}, SKU: {sp._data.get('SKU', 'N/A')}")

            try:
                from inventree.purchase_order import PurchaseOrderLineItem

                po_lines = PurchaseOrderLineItem.list(api, part=sp.pk)
            except Exception as e:
                print(f"    Error fetching PO line items: {e}")
                continue

            if not po_lines:
                print("    No purchase order line items found for this supplier part.")
                continue

            for line in po_lines:
                try:
                    order_id = line._data.get("order")
                    from inventree.purchase_order import PurchaseOrder

                    order = PurchaseOrder(api, pk=order_id)
                    status = order._data.get("status", "Unknown")
                    ref = order._data.get("reference", "No Ref")
                    print(
                        f"    PO Line ID: {line.pk}, Order Ref: {ref}, Status: {status}"
                    )
                except Exception as e:
                    print(f"    Error fetching order for PO line {line.pk}: {e}")


if __name__ == "__main__":
    main()
