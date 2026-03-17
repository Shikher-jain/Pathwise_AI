from __future__ import annotations

RAW_COMPANIES = """
foundit
google
turing
fractal
ericsson
ebay
dhl
cisco
capgemini
ibm
microsoft
mercor
citi
apple
wipro
philips
oracle
iqigai
infosys
hcltech
exl
barclays
accenture
unilever
UiPath
tcs
tata
SwiftSafe
sound credit union
Risen -
pepsico
Optimspace
Newton School
Neon AI Limited
mircon
meta
Master-Works
Kyndryl India
Hackveda
grab
gemini solution
gartner
ey
drdo
criteo
cargill
Birdeye
automationanywhere
Auto desk
atlassian
american express
amazon
allstate
adobe
zscaler
zomato
zoho
zocdoc
zinier
zepto
zee
Zabbix
z2
wquifax
world bank
Wisdom Jobs (Recruitment Tech)
wintwealth
wesco
Walmart
wadhwani entreprisis
volvo
visa
virtusa
Versor Investments
upwork
upsun
Upstox (growing tech)
United Airlines
unipath
Uncapped
Unacademy (smaller teams)
uber
trust bank
tower
timejobs
thales
Tesla
teradata
temenous
telus
tekion
TeamLease Services
tcs ibegin
tata steel
swiss re
swiggy
superset
stripe
straive
steer health
stable money
spotify
Splunk
speechify
soul ai
Sokrati/AI Startup Teams
Smallcase
skill scout
skill india
simpl
Shuttl
shopify
shine
salasforce
s&p global
rubrik
rippling
Razorpay
rapido
ralliant
quickhyre
Qube Research
qualys
qualcomm
qode
qlik
pwc
pubmatic
prolegion
Postman
Point72 (Tech roles India)
pivaga
PhonePe
persistent
pega
Paytm
paypal
paradox
pairteam
orion
optum
openai
ola
nvidia
ntt
novarties
niyo
nexus consulting
netflex
nestle
neenopal
natwest
nagarro
Mu Sigma
MoEngage
Millennium Management India
MetBrains Inc.
met life
messho
merck
Mercer
megha minds
megha international
Meesho
mathco
master card
ltv plus
Ltimindtree
lowe's
Lingaro
kuehne nagel
KPMG India
Korcomptenz India
kelpr
kagool
jp morgan
jobgether
itcdac
isro
irth
intel
Insight Global
Infra.Market
inficore soft
iff
ielts
icims
hp
honeywell
hll
harvey
harmony ai
happyfox
guvi
Groww (if you want internal roles)
GoodSpace AI
goldman sachs
global logic
gitlab
genpact
geekyant
ge vernova
GE Aerospace
Freshworks
forage
flipkart
fingerprint
fidelety
fedex
facebook
Explocity
evnek
endee
elevate
elba
eight fold
eict
Dymon Asia
duckduck go
docker
digitalocean
dic
Dexlock
Dexian India
dentsu
deloitte
databricks
danaher
cyient
Cutshort (Hiring Platform)
crossing hurdles
CRED Growth/Exp Ops
coupang
coriolis tech
convr
coinbase
Cognizant
cogent
coforge
codec research
Clovity
claude
Chargebee
cashfree
careersatech
capco
canonical
bytedance
BrowserStack
broadway infotech
bosch
bnb paribas
blueyonder
Blowhorn
blinkit
Blackcoffer
BlackBuck
baker hughes
averixis
avast
atlan
astraya
assystem
aptiv
anthropic
anblicks
amgen
altimetrik
alteria capital
Alignerr
alacriti
AirVeda
airtm
airbnb
ags
"""


def get_target_companies(max_items: int | None = None) -> list[str]:
    """Return cleaned unique company names from the seed list."""
    seen: set[str] = set()
    cleaned: list[str] = []

    for raw in RAW_COMPANIES.splitlines():
        name = " ".join(raw.strip().strip("-").split())
        if not name:
            continue

        key = name.casefold()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(name)

    return cleaned[:max_items] if max_items else cleaned
