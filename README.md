# Public source feeds

This repository collects approved public Humoruniv posts in `feed.json` and recent highlight links from official sports-rights-holder YouTube channels in `highlights.json`.

The highlight collector checks Coupang Play Sports, SPOTV, NBA, and KBO. It filters selected marquee team names across football, baseball, basketball, and volleyball. Korean Series and NBA Finals/Cup/Playoffs highlights qualify as major events even when neither team matches the curated list.

The private publisher uses these official-channel candidates to post recent full-match highlights and connect each post to AI Time Machine with team, league, and date fields. The publisher does not add scores or game summaries; the site handles match details. Individual KBO moment clips are excluded.

The collector reads titles and descriptions from each official YouTube channel feed. The private publisher checks those fields for the match date and kickoff time; it does not collect separate league schedules. It has no destination-site address, account, password, API key, or publishing code. Posting settings stay in the private `nude-tv-free-board-automation` repository.
