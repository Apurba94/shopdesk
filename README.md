# ShopDesk

Billing and stock for a small shop, on one offline computer: quick bills, customer credit (baki), true profit, and what to buy next.

```
python -m shopdesk
```

Then open http://127.0.0.1:8046. It needs Python 3.10 or newer.

## What it does

- **Bills** with discounts, and loose quantities such as 1.5 kg. Stock falls by itself, and you cannot sell more than you hold
- **True profit:** cost uses the weighted average, so profit stays right when buying prices change
- **Customer credit:** balances, payments and how old the oldest unpaid amount is
- **Buy soon:** items at their reorder level, or running out within a week at the recent selling speed, with a suggested quantity
- **Slow stock:** money tied up in goods that are not selling
- **Price warnings:** selling below cost, or at a very thin margin
- **Printable receipts,** through the browser's print command

Money is held as whole paisa, so totals are always exact.

## How it is tested

Average cost, bills, tax after discount, credit ageing and reorder rules are tested on worked examples. App tests run a sale end to end and confirm that a failed sale changes nothing, and that a customer cannot pay more than they owe.

## Limits

One shop, one computer, no barcode scanner support and no staff logins. There is no tax return reporting, so check rules with an accountant. Bills cannot be edited or returned yet. Keep a copy of the file, because it is the only copy of your records.

## Tests

```
python -m unittest discover -s tests
```

MIT licence.
