# newstock-alert-bot

A stock alert bot designed to support multiple shopping marketplaces through a
shared adapter contract.

## Marketplace architecture

Marketplace integrations must implement the `BaseMarketplace` contract from
`newstock_alert_bot.marketplaces`. The bot should depend on this interface only,
so adding Amazon, Flipkart, Croma, AJIO, Meesho, Zepto, Instamart, BigBasket,
Savana, or another marketplace does not require changes to the alerting flow.

Every adapter returns the common `ProductSnapshot` data model with:

- Product Name
- Product URL
- Product ID
- Current Price
- MRP
- Discount Percentage
- Stock Status
- Delivery Available
- Delivery PIN Code
- Seller Name
- Image URL
- Marketplace Name
- Last Checked Time

No concrete shopping website implementation is included yet.
