"""Read-only location estimates and IANA conversions; never assert office opening hours."""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from zoneinfo import ZoneInfo
from src.backend.db.connection import create_connection

with (Path(__file__).parent / 'timezone_data' / 'America_Winnipeg.tzif').open('rb') as source:
    WINNIPEG = ZoneInfo.from_file(source, key='America/Winnipeg')

# Single-zone regions. Split-zone regions require a recognized city below.
REGIONS = {
    'America/New_York': 'US: Connecticut CT, Delaware DE, Georgia GA, Maine ME, Maryland MD, Massachusetts MA, New Hampshire NH, New Jersey NJ, New York NY, North Carolina NC, Ohio OH, Pennsylvania PA, Rhode Island RI, South Carolina SC, Vermont VT, Virginia VA, West Virginia WV, Washington DC',
    'America/Chicago': 'US: Alabama AL, Arkansas AR, Illinois IL, Iowa IA, Louisiana LA, Minnesota MN, Mississippi MS, Missouri MO, Oklahoma OK, Wisconsin WI',
    'America/Denver': 'US: Colorado CO, Montana MT, New Mexico NM, Utah UT, Wyoming WY',
    'America/Los_Angeles': 'US: California CA, Nevada NV, Washington WA',
    'America/Toronto': 'Canada: most Ontario ON and Quebec QC cities; city confirmation required',
    'America/Winnipeg': 'Canada: Manitoba MB; northwestern Ontario ON (Dryden, Fort Frances, Kenora)',
    'America/Edmonton': 'Canada: Alberta AB, Northwest Territories NT',
    'America/Vancouver': 'Canada: most British Columbia BC cities; local exceptions exist',
    'America/Halifax': 'Canada: New Brunswick NB, Nova Scotia NS, Prince Edward Island PE',
    'America/St_Johns': 'Canada: Newfoundland; Labrador NL has different zones',
    'America/Regina': 'Canada: Saskatchewan SK, except Lloydminster area',
    'America/Phoenix': 'US: most Arizona AZ; Navajo Nation follows different clock rules',
    'America/Anchorage': 'US: most Alaska AK; western Aleutians use another zone',
    'Pacific/Honolulu': 'US: Hawaii HI',
    'America/Whitehorse': 'Canada: Yukon YT',
    'America/Atikokan': 'Canada: Atikokan ON, year-round Eastern standard time',
    'America/Creston': 'Canada: Creston and Wynndel BC',
    'America/Iqaluit': 'Canada: eastern Nunavut NU, including Iqaluit',
    'America/Rankin_Inlet': 'Canada: central Nunavut NU, including Rankin Inlet',
    'America/Cambridge_Bay': 'Canada: western Nunavut NU, including Cambridge Bay',
    'America/Adak': 'US: western Aleutian Islands, Alaska AK, including Adak',
}
REGIONS['America/New_York'] += '; parts of Florida FL, Indiana IN, Kentucky KY, Michigan MI and Tennessee TN — check the city'
REGIONS['America/Chicago'] += '; parts of Florida FL, Indiana IN, Kentucky KY, Michigan MI, Tennessee TN, Kansas KS, Nebraska NE, North Dakota ND, South Dakota SD and Texas TX — check the city'
REGIONS['America/Denver'] += '; parts of Idaho ID, Oregon OR, Kansas KS, Nebraska NE, North Dakota ND, South Dakota SD, Texas TX and Nevada NV (West Wendover) — check the city'
REGIONS['America/Los_Angeles'] += '; most Oregon OR and northern Idaho ID — check the city; Nevada West Wendover uses Mountain time'
REGIONS['America/Halifax'] += '; parts of Labrador NL, including Happy Valley-Goose Bay; Quebec QC has local exceptions'
LABELS = {
    'America/New_York':'Eastern · US', 'America/Toronto':'Eastern · Canada',
    'America/Chicago':'Central · US', 'America/Winnipeg':'Central · Canada',
    'America/Denver':'Mountain · US', 'America/Edmonton':'Mountain · Canada',
    'America/Los_Angeles':'Pacific · US', 'America/Vancouver':'Pacific · British Columbia',
    'America/Halifax':'Atlantic', 'America/St_Johns':'Newfoundland',
    'America/Regina':'Saskatchewan · year-round', 'America/Phoenix':'Arizona · year-round',
    'America/Anchorage':'Alaska', 'Pacific/Honolulu':'Hawaii',
    'America/Whitehorse':'Yukon · year-round', 'America/Atikokan':'Atikokan · year-round',
    'America/Creston':'Creston · year-round',
    'America/Iqaluit':'Eastern · Nunavut', 'America/Rankin_Inlet':'Central · Nunavut',
    'America/Cambridge_Bay':'Mountain · Nunavut', 'America/Adak':'Western Aleutians',
}
US_ZONES = ['America/New_York','America/Chicago','America/Denver','America/Los_Angeles',
            'America/Phoenix','America/Anchorage','Pacific/Honolulu','America/Adak']
COUNTRY_ZONES = {'US': US_ZONES, 'CA': [z for z in REGIONS if z not in US_ZONES]}
SINGLE = {}
for zone, states in {
    'America/New_York': 'CT DE GA ME MD MA NH NJ NY NC OH PA RI SC VT VA WV DC',
    'America/Chicago': 'AL AR IL IA LA MN MS MO OK WI',
    'America/Denver': 'CO MT NM UT WY', 'America/Los_Angeles': 'CA NV WA',
    'Pacific/Honolulu': 'HI', 'America/Winnipeg': 'MB',
    'America/Edmonton': 'AB NT', 'America/Halifax': 'NB NS PE', 'America/Whitehorse': 'YT',
}.items():
    for state in states.split():
        SINGLE[state] = zone

CITIES = {}
def cities(state, zone, names):
    for name in names.split('|'):
        CITIES[state, name.casefold()] = zone

cities('ON', 'America/Toronto', 'Windsor|Toronto|Thunder Bay|Bath|Beamsville|Blenheim|Bolton|Bowmanville|Bradford West Gwillimbury|Brampton|Brantford|Burlington|Cambridge|Carp|Chapleau|Chatham|Chelmsford|Chepstow|Cochrane|Concord|Dresden|Dundas|Eganville|Etobicoke|Georgetown|Glencoe|Guelph|Haliburton|Hamilton|Harcourt|Harley|Harrow|Ilderton|Innisfil|Kanata|Kapuskasing|Kilworthy|Kingston|Kitchener|LaSalle|Lakeshore|Lindsay|London|Madawaska|Midland|Milton|Mindemoya|Mississauga|Mount Brydges|Nairn Centre|Nanticoke|Niagara Falls|North Bay|Oakville|Oldcastle|Ottawa|Paris|Princeton|Puslinch|Rodney|Ruscom Station|Salford|Sault Ste. Marie|Scarborough|Shallow Lake|Springfield|St. Catharines|St. Thomas|Stoney Creek|Stratford|Sudbury|Thedford|Thessalon|Tillsonburg|Timmins|Utopia|Wainfleet|Wallaceburg|Waterloo|Welland|Whitney|Woodbridge|Woodstock')
cities('ON', 'America/Winnipeg', 'Dryden|Fort Frances|Kenora')
cities('ON', 'America/Atikokan', 'Atikokan|Pickle Lake')
cities('QC', 'America/Toronto', 'Montreal|Montréal|Quebec|Québec|Amos|Anjou|Bedford|Boucherville|Brossard|Chapais|Chertsey|Chibougamau|Chicoutimi|Drummondville|Granby|LaSalle|Lachine|Landrienne|Laval|Levis|Lévis|Longueuil|Mont-Joli|Mont-Saint-Hilaire|Montmagny|Pointe-Claire|Saint-Alexis-des-Monts|Saint-Anselme|Saint-Apollinaire|Saint-Bruno-de-Montarville|Saint-Cesaire|Saint-Césaire|Saint-Cuthbert|Saint-Damien-de-Buckland|Saint-Eustache|Saint-Georges|Saint-Hyacinthe|Saint-Jerome|Saint-Jérôme|Saint-Laurent|Saint-Pie|Saint-Raymond|Sainte-Claire|Sainte-Julie|Sherbrooke|Terrebonne|Trois-Rivieres|Trois-Rivières|Val-d’Or|Val-d\'Or|Victoriaville')
cities('BC', 'America/Vancouver', 'Vancouver|Abbotsford|Armstrong|Barriere|Burnaby|Burns Lake|Castlegar|Chemainus|Delta|Duncan|Fort St. James|Grand Forks|Kamloops|Langley|Maple Ridge|Mission|Port Coquitlam|Prince George|Quesnel|Revelstoke|Richmond|Salmo|Smithers|Strathnaver|Surrey|Vanderhoof|West Kelowna|Westbank|Williams Lake')
cities('BC', 'America/Edmonton', 'Galloway|Radium Hot Springs|Cranbrook')
cities('BC', 'America/Creston', 'Creston|Wynndel')
cities('SK', 'America/Regina', 'Saskatoon|Regina|Prince Albert|Big River|Hudson Bay|Meadow Lake')
cities('SK', 'America/Edmonton', 'Lloydminster')
cities('AZ', 'America/Phoenix', 'Phoenix|Tucson|Mesa')
cities('AK', 'America/Anchorage', 'Anchorage|Fairbanks|Juneau')
cities('NL', 'America/St_Johns', "St. John's|St. John’s|Corner Brook")
cities('FL', 'America/New_York', 'Bartow|Bristol|Cross City|Debary|Delray Beach|Fort Lauderdale|Havana|Jacksonville|Lake Worth|Ocala|Orlando|Spring Hill|Miami')
cities('FL', 'America/Chicago', 'Pensacola|Panama City')
cities('IN', 'America/New_York', 'Akron|Bargersville|Bloomington|Butler|Columbia City|Crawfordsville|Edinburgh|Elkhart|Fort Wayne|Frankfort|Greencastle|Greenfield|Indianapolis|Jeffersonville|Lafayette|Logansport|Madison|Martinsville|Milford|New Albany|Noblesville|Saint Joe|Sellersburg|Shelbyville|Shoals|South Bend|Union City|Whitestown')
cities('IN', 'America/Chicago', 'Boonville|East Chicago|Evansville|Gary|Hammond|Portage|Porter')
cities('IN', 'America/New_York', 'Francesville')
cities('KY', 'America/New_York', 'Frankfort|Jeffersontown|Lexington|Louisville|Morehead|Shelbyville|Silver Grove|Somerset|South Shore|Winchester')
cities('KY', 'America/Chicago', 'Bowling Green|Fordsville|Franklin|Owensboro|Russell Springs')
cities('MI', 'America/New_York', 'Warren|Detroit|Auburn Hills|Bay City|Brighton|Clarkston|Clinton Township|Constantine|Dearborn|Farmington Hills|Flat Rock|Flint|Fraser|Freeport|Gladstone|Gobles|Grand Haven|Grand Rapids|Grandville|Highland|Holland|Jackson|Kalamazoo|Livonia|Macomb|Madison Heights|Manistee|Mason|Milan|Monroe|Muskegon|New Haven|Pewamo|Plymouth|Potterville|Remus|Romeo|Roseville|Royal Oak|Saint Johns|Sterling Heights|Sunfield|Troy|Winn|Wixom|Zeeland')
cities('MI', 'America/Chicago', 'Iron Mountain|Ironwood')
cities('KS', 'America/Chicago', 'Hutchinson|Lawrence|Overland Park|Salina|Shawnee|Wathena')
cities('NE', 'America/Chicago', 'Columbus|Fremont|Grand Island|Kearney|Omaha|Valley')
cities('ND', 'America/Chicago', 'Fargo|Bismarck')
cities('SD', 'America/Chicago', 'Sioux Falls|Aberdeen|Watertown')
cities('SD', 'America/Denver', 'Rapid City')
cities('TX', 'America/Chicago', 'Houston|Dallas|Fort Worth|Austin|San Antonio|Lubbock|Amarillo|Waco|Tyler')
cities('TX', 'America/Denver', 'El Paso')
cities('TN', 'America/Chicago', 'Nashville|Memphis|Jackson|Clarksville|Cookeville')
cities('TN', 'America/New_York', 'Knoxville|Chattanooga|Johnson City|Bristol')
cities('ID', 'America/Denver', 'Boise|Caldwell|Eden|Idaho Falls')
cities('ID', 'America/Los_Angeles', 'Grangeville|Laclede|Princeton|Lewiston')
cities('OR', 'America/Los_Angeles', 'Boring|Canby|Cave Junction|Clackamas|Corvallis|Dayton|Eugene|Gaston|Glendale|Grants Pass|Lyons|Monroe|Portland|Springfield')
cities('OR', 'America/Denver', 'Ontario')
cities('NU', 'America/Iqaluit', 'Iqaluit')
cities('NU', 'America/Rankin_Inlet', 'Rankin Inlet')
cities('NU', 'America/Cambridge_Bay', 'Cambridge Bay')
cities('AK', 'America/Adak', 'Adak')
cities('NL', 'America/Halifax', 'Happy Valley-Goose Bay')
cities('NV', 'America/Denver', 'West Wendover')
cities('QC', 'America/Toronto', "Saint-Edouard-de-Lotbiniere|Saint-Elzear|Saint-Ephrem-de-Beauce|Saint-Eugene|Saint-Félicien|Saint-Gedeon-de-Beauce|Saint-Honore-de-Temiscouata|Saint-Hubert|Saint-Jean-Port-Joli|Saint-Jean-sur-Richelieu|Saint-Joseph-de-Kamouraska|Saint-Just-de-Bretenières|Saint-Leonard|Saint-Ludger-de-Milot|Saint-Michel-des-Saints|Saint-Pamphile|Saint-Paul-d'Abbotsford|Saint-Prime|Sainte-Foy|Sainte-Justine|Sainte-Marie|Sainte-Perpetue|Sainte-Therese|Shipshaw|Squatec|Thetford Mines|Témiscaming|Val-des-Bois|Vercheres|West Brome|Windsor|Yamachiche")
cities('SD', 'America/Chicago', 'Brookings|Mitchell')
cities('SK', 'America/Regina', 'Glaslyn|St. Brieux')
cities('TN', 'America/Chicago', 'Centerville|Collinwood|Huntland|Linden|Murfreesboro|Oakland')
cities('TN', 'America/New_York', 'Athens')
cities('TX', 'America/Chicago', 'Arlington|Ballinger|Bertram|Brookshire|Carrollton|Cleburne|Corrigan|Corsicana|Euless|Garland|Graham|Grandview|Irving|Livingston|Longview|Lufkin|North Richland Hills|Seguin|Somerset|Spring|Sweetwater')

def zone_for(facility):
    state = (facility.get('state_prov') or facility.get('state') or '').strip().upper()
    country = (facility.get('country') or '').upper()
    if country and country not in {'US', 'USA', 'CA', 'CANADA'}:
        return None
    return CITIES.get((state, (facility.get('city') or '').strip().casefold())) or SINGLE.get(state)

def within_hours(zone, at=None, start=9, end=17):
    if not zone:
        return False
    instant = at or datetime.now(timezone.utc)
    local = instant.astimezone(timezone_for(zone, instant))
    return local.weekday() < 5 and start <= local.hour < end

def timezone_for(zone, at):
    # Published Windows tzdata package predates 2026e; see timezone_data/SOURCE.md.
    return WINNIPEG if zone == 'America/Winnipeg' else ZoneInfo(zone)

def clock_data(at=None):
    at = at or datetime.now(timezone.utc)
    return {'at': at.isoformat(), 'zones': {zone: {
        'offset': int(at.astimezone(timezone_for(zone, at)).utcoffset().total_seconds() / 60),
        'label': at.astimezone(timezone_for(zone, at)).tzname(),
        'regions': regions,
        'name': LABELS[zone],
    } for zone, regions in REGIONS.items()}}

def matching_companies(allowed, zone=None, open_now=False, start=9, end=17):
    if not zone and not open_now:
        return allowed
    with closing(create_connection()) as conn:
        rows = conn.execute('SELECT company_id,city,state_prov,country FROM facilities').fetchall()
    at = datetime.now(timezone.utc)
    matched = {row['company_id'] for row in rows if
               (resolved := zone_for(dict(row))) and (not zone or resolved == zone)
               and (not open_now or within_hours(resolved, at, start, end))}
    return sorted(matched if allowed is None else matched.intersection(allowed))

def annotate(group, zone=None, open_now=False, start=9, end=17):
    for facility in group.get('facilities', []):
        facility['calling_zone'] = zone_for(facility)
    primary = next((f for f in group.get('facilities', []) if f.get('facility_id') == group.get('primary_facility_id')), None)
    group['calling_zone'] = primary.get('calling_zone') if primary else None
    if zone or open_now:
        at = datetime.now(timezone.utc)
        group['calling_matches'] = [f.get('facility_id') for f in group.get('facilities', [])
            if f.get('calling_zone') and (not zone or f['calling_zone'] == zone)
            and (not open_now or within_hours(f['calling_zone'], at, start, end))]
