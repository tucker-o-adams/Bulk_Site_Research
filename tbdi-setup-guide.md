# Mireye Setup Guide

Get Claude Code connected to Mireye and run your first cited site screen. 

---

## 1. Create your Mireye account

Go to **[https://www.mireye.com/signup](https://www.mireye.com/signup)** and sign up with Google or email.

The free tier gives you **5,000 credits/month, no card required** — enough to verify the setup and run a few full site screens before you pick a plan.

## 2. Connect Claude Code to Mireye (one command, no API key)

In your terminal:

```bash
claude mcp add --transport http --scope user mireye-earth https://api.mireye.com/mcp
```

Then:

1. Restart Claude Code.
2. Type `/mcp` inside Claude Code.
3. Select **mireye-earth** and complete the browser sign-in (it uses the account from step 1).

That's it. Claude now has seven Mireye tools (`mireye_lookup`, `mireye_fetch`, `mireye_ask`, `mireye_geocode`, `mireye_proximity`, and two field-request tools) and can discover the full field catalog on its own — you never have to read the catalog manually.

> There is no API key to copy-paste for this path. The browser sign-in handles it. API keys only matter if Tucker later scripts against the HTTP API directly (see step 6).

## 3. Give Claude the Mireye instructions

Save the file we sent — **`mireye-instructions-tbdi.md`** — as **`CLAUDE.md`** inside the folder where you run Claude Code for site screening (e.g. `~/tbdi-screening/CLAUDE.md`).

Claude Code automatically reads `CLAUDE.md` from the working folder at the start of every session, so Claude will always know the screening recipe, the field conventions, and the credit costs without you re-explaining anything. If you already have a `CLAUDE.md` there, paste the contents at the end of it.

## 4. Verify it works (costs ~10 credits)

Start Claude Code in that folder and ask:

> Using Mireye, what's the FEMA flood zone and how far is the nearest substation at 40.155, -82.75? Cite sources.

You should get an answer with values, source names (FEMA NFHL, EIA), and confidence ratings. If you do, you're live.

## 5. Run your first real screen

Paste an address or coordinate from your Ohio/Iowa batch:

> Run a full data center site screen on [ADDRESS or LAT, LNG]. Follow the screening recipe.

Claude will resolve the parcel, pull the data center siting preset, hazards, and utilities, and give you a verdict with every number cited. First one takes a couple of minutes; expect roughly 750–800 credits per full screen.

### More starter queries

- **Batch triage** (the 200 → 20 cut):
  > Here are 10 sites from our batch: [list of addresses or coordinates]. Run the triage screen on each and give me a ranked GO / REVIEW / NO-GO table with the reason for each verdict.
- **Who's the utility:**
  > Which electric utility serves [SITE], how far is the nearest substation and at what voltage, and how much interconnection queue is active in this county?
- **Hazards only:**
  > Run the natural hazard preset on [SITE] — seismic, wind, tornado, hail, flood, dams — and flag anything a data center design would care about.
- **Buildable acres:**
  > For [SITE]: parcel size, zoning, how much of the parcel is wetland, and the developable-acres estimate. Show the parcel geometry facts.
- **Neighborhood fit (Davis's coffee filter):**
  > For [SITE]: how many housing units are within 1 km, what's the residential context class, and how far is the nearest school? Anything nearby that makes this a bad neighbor?

## 6. API access for scripting 

If you want to run sites through code instead of chat:

- Create an API token at **[https://www.mireye.com/account?tab=tokens](https://www.mireye.com/account?tab=tokens)** (90-day tokens, shown once — store it as `MIREYE_API_TOKEN`).
- Base URL `https://api.mireye.com`, header `Authorization: Bearer $MIREYE_API_TOKEN`.
- `POST /v1/fetch/batch` takes one field selection × up to 25 locations per call, and `POST /v1/runs` handles bigger async jobs with CSV/GeoJSON artifacts — these two are HTTP-only (not in the MCP), and they're the main reason to have a token at all.
- One thing to know: the MCP browser sign-in and API tokens are separate credentials. The MCP one won't work for direct HTTP calls — use a dashboard token there.
- Full reference: **[https://docs.mireye.ai](https://docs.mireye.ai)** (quickstart, every endpoint, errors) and the machine-readable catalog at `GET https://api.mireye.com/v1/meta/fields` (public, no auth).

## 7. Credits and plans

Everything is credit-metered. The short version:


| Call                                             | Credits      |
| ------------------------------------------------ | ------------ |
| Fetch a data field                               | 1 per field  |
| Natural-language question (`mireye_ask`)         | 10           |
| Parcel record (geometry, zoning, owner, acreage) | 300 per site |
| Full TBDI site screen (parcel + ~150 fields)     | ~750–800     |
| Triage screen (no parcel record, preset only)    | ~110         |



| Plan   | Price   | Credits/month |
| ------ | ------- | ------------- |
| Free   | $0      | 5,000         |
| Build  | $19/mo  | 25,000        |
| Growth | $99/mo  | 120,000       |
| Scale  | $499/mo | 750,000       |


Overage on paid plans is a flat $1 per 1,000 credits. Live price list: `GET https://api.mireye.com/v1/meta/plans`. Your balance: the **Usage** tab at mireye.com/account.

What that means for your workflow: **a 50-site month of full screens is ~38,000 credits — inside the $99 Growth plan.** The full 200-site batch is ~150,000 credits (Growth + ~$30 overage, or Scale). Running all 2,800 raw sites through the *triage* screen is ~300,000 credits — also well within reach. Cost is not the constraint.

The power estimate (deliverable-MW band), owner/contact finder, and county friendliness read (moratoriums, town-hall sentiment, incentives) are separate contract capabilities on top of this — that's the quote conversation with Ansh.

## 8. If something breaks

- `/mcp` shows mireye-earth disconnected → restart Claude Code, run `/mcp`, re-auth in the browser.
- 401 errors → the sign-in expired; re-auth the same way.
- A natural-language question takes up to 60 s on the first call of the day (cold start) — that's normal.
- Free tier is rate-limited to 20 requests/minute; paid plans raise this a lot (Growth is 300/min).
- Docs: [https://docs.mireye.ai/mcp/troubleshooting](https://docs.mireye.ai/mcp/troubleshooting) — or just message Ansh.

