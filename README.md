# Holloman Exterminators Inventory App

Simple inventory tracking app for pest control operations.

## Setup

1. Install Python 3
2. Install requirements:
   pip install -r requirements.txt

3. Run app:
   python app.py

4. Open browser:
   http://127.0.0.1:5000

## What it does
- Track inventory
- Receive orders
- Log technician usage
- Auto calculate stock
- Reorder recommendations

## Notes
- Uses SQLite (inventory.db file)
- No external setup required

## Next Improvements
- Reporting
- CSV export
- Better UI
- Mobile optimization

## Independent app boundary

Inventory owns inventory, receiving, stock, usage, and reordering. OpsBrain is the operations hub and may link to this application. SalesBrain owns sales, leads, quotes, proposals, and signatures; BugManGraphs owns graphing, measurements, and site plans. Integrate through holloman-mcp and approved shared APIs rather than copying app source.

The existing Python/SQLite implementation remains the current implementation; this boundary definition does not migrate its data or introduce a new stack. PestPac remains the system of record for its customer, service, scheduling, and billing records. Do not duplicate those records or introduce production writes without an approved integration contract. A future inspection app gets its own unique name and repository.
