# Public source feeds

This repository collects approved public Humoruniv posts in `feed.json` and recent highlight links from official sports-rights-holder YouTube channels in `highlights.json`.

The highlight collector checks Coupang Play Sports, SPOTV, NBA, and KBO. It filters selected marquee team names across football, baseball, basketball, and volleyball. Korean Series and NBA Finals/Cup/Playoffs highlights qualify as major events even when neither team matches the curated list.

The private publisher embeds new videos from these official channels in NUTV's highlights board. The site's existing video handling displays the YouTube embed. Individual KBO moment clips are excluded.

This public repository only discovers and stores highlight video links. It does not collect match schedules or contain the destination site's address, account, password, API key, or posting code. Posting settings stay in the private `nude-tv-free-board-automation` repository.
