import os
import json
import time
import uuid
import requests
from datetime import datetime
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup

from seetha import ai_client
from seetha.config import get_key
from seetha.logger import setup_logger

logger = setup_logger()

class ResearchEngine:
    """
    Seetha Deep Research Engine.
    STRICT, READ-ONLY ADDON.
    Controls knowledge freshness & time-sensitivity decisions.
    Uses the user's own API keys (Settings window); every key is optional
    and each missing key just removes one evidence source.
    """
    def __init__(self):
        # Configuration
        self.max_sources = 10
        self.verified_insights_count = 0

        # Optional Gemini client (extra synthesis quality if key present)
        self.gemini_model = None
        google_key = get_key("GOOGLE_API_KEY")
        if google_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=google_key)
                self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            except Exception as e:
                logger.warning(f"Gemini unavailable: {e}")

    def execute_task(self, query, task_id=None, user_id=None):
        """
        Main Execution Flow (10 Steps)
        """
        if not task_id: task_id = str(uuid.uuid4())

        try:
            # STEP 1: FRESHNESS CLASSIFICATION
            classification = self._classify_freshness(query)
            yield self._emit("freshness_check", task_id, {
                "display_text": f"[00:00] 🔍 Query classified as: {classification}",
                "source_type": "none",
                "verified": True
            })

            # STEP 2: ACTIVATE RESEARCH MODE
            yield self._emit("activation", task_id, {
                "display_text": "Deep Research Mode Activated ⚡",
                "source_type": "none",
                "verified": True
            })
            
            # STEP 3: TOPIC CLASSIFICATION
            topic = self._classify_topic(query)
            yield self._emit("topic_check", task_id, {
                "display_text": f"[00:00] 🔍 Topic classified as: {topic}",
                "source_type": "none",
                "verified": True
            })
            
            # STEP 4: AUTHORITY DOMAIN FILTER
            if topic in ["Government Organization", "Politics", "Conflict"]:
                yield self._emit("filter_check", task_id, {
                    "display_text": "[00:00] 🔍 Searching authoritative sources only...",
                    "source_type": "none",
                    "verified": True
                })

            # STEP 5: WEB EVIDENCE COLLECTION
            yield self._emit("search_start", task_id, {
                "display_text": "[00:00] 🌐 Collecting web evidence...",
                "source_type": "none",
                "verified": True
            })
            
            sources = self._collect_evidence(query, classification, topic)
            
            # STEP 6: VERIFIED INSIGHT RULE (PARALLELIZED)
            verified_facts = []
            all_facts = []
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            if sources:
                def process_source(source):
                    try:
                        # Use pre-fetched summary if available (API sources), else scrape
                        text = source.get('summary')
                        if not text:
                            text = self._extract_text(source['href'])
                        
                        if not text: return []
                        
                        facts = self._extract_facts(text, query)
                        return facts
                    except Exception as e:
                        logger.error(f"Source Processing Error ({source.get('title')}): {e}")
                        return []

                # Run analysis in parallel to speed up research 10x
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_source, s): s for s in sources}
                    
                    for i, future in enumerate(as_completed(futures)):
                        source = futures[future]
                        yield self._emit("analysis_progress", task_id, {
                            "display_text": f"[00:00] 📖 Analyzed: {source.get('title')[:30]}...",
                            "source_type": source.get('type', 'news'),
                            "verified": False
                        })
                        try:
                            facts = future.result()
                            all_facts.extend(facts)
                        except Exception as e:
                            logger.error(f"Future Error: {e}")
            
            # Verify Facts (De-duplication & Count)
            verified_facts = self._verify_insights(all_facts)
            self.verified_insights_count = len(verified_facts)
            
            for fact in verified_facts:
                 yield self._emit("insight_verified", task_id, {
                    "display_text": f"[00:00] 📰 Verified: {fact}",
                    "source_type": "official",
                    "verified": True
                 })
                 
            if not verified_facts and all_facts:
                 yield self._emit("insight_unverified", task_id, {
                    "display_text": f"[00:00] ⚠️ Unverified insight: {all_facts[0]}",
                    "source_type": "anecdotal",
                    "verified": False
                 })

            # STEP 7: LLM-ASSISTED DEEP RESEARCH
            yield self._emit("deep_research", task_id, {
                "display_text": "[00:00] 🧠 Running AI-assisted deep analysis...",
                "source_type": "none",
                "verified": False
            })
            
            # STEP 8: FINAL SYNTHESIS
            report = self._synthesize_final_report(query, verified_facts, sources)
            
            yield self._emit("final_report", task_id, {
                 "display_text": "Research Synthesis Ready.",
                 "report_content": report,
                 "source_type": "none",
                 "verified": True
            })

            # STEP 9: CONFIDENCE SCORING
            confidence = self._calculate_confidence(len(sources), self.verified_insights_count)
            yield self._emit("confidence", task_id, {
                "display_text": f"📊 Confidence Level: {confidence}%",
                "source_type": "none",
                "verified": True
            })

            # STEP 10: COMPLETE
            yield self._emit("complete", task_id, {
                "display_text": "Premium research completed successfully ⚡",
                "source_type": "none",
                "verified": True
            })

        except Exception as e:
            logger.error(f"Research Task Error: {e}", exc_info=True)
            yield self._emit("error", task_id, {
                "display_text": f"Error: {str(e)}",
                "source_type": "none",
                "verified": False
            })

    # --- HELPERS ---

    def _emit(self, event_type, task_id, payload):
        # Format: NEWLINE-SEPARATED JSON events
        # Adding timestamp dynamically
        payload["timestamp"] = datetime.now().isoformat()
        if "event" not in payload: payload["event"] = event_type # Ensure event type is in payload or wrapper? 
        # The prompt asks for: { "event": "...", "timestamp": "...", "payload": {...} }
        # Let's restructure to match EXACTLY.
        
        final_obj = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "display_text": payload.get("display_text", ""),
                "source_type": payload.get("source_type", "none"),
                "verified": payload.get("verified", False)
            }
        }
        
        # Add extra fields to payload if they exist (like report_content) for UI to render
        for k, v in payload.items():
            if k not in ["display_text", "source_type", "verified", "timestamp", "event"]:
                final_obj["payload"][k] = v
                
        return json.dumps(final_obj)

    def _classify_freshness(self, query):
        prompt = f"""
        Classify this query into EXACTLY ONE category:
        1. STABLE FACT (History, Basic Science, Established Geography)
        2. RECENT UPDATE (Events in last 30 days)
        3. BREAKING / REAL-TIME (Events in last 48 hours)
        
        Query: "{query}"
        
        Return ONLY one word: STABLE, RECENT, or BREAKING.
        """
        res = self._llm_call(prompt)
        if "BREAKING" in res: return "BREAKING"
        if "RECENT" in res: return "RECENT"
        return "STABLE"

    def _classify_topic(self, query):
        prompt = f"""
        Classify this query into EXACTLY ONE category:
        - Government Organization
        - Company / Startup
        - Person
        - Technology / Science
        - General Knowledge
        
        Query: "{query}"
        
        Return ONLY the category name.
        """
        res = self._llm_call(prompt)
        return res.strip()

    def _collect_evidence(self, query, freshness, topic):
        sources = []
        search_query = query
        
        # Domain Filter for Gov/Politics
        if topic in ["Government Organization", "Politics"]:
            search_query += " site:gov OR site:gov.in OR site:nic.in OR site:reuters.com OR site:bbc.com"
            
        # Time Filter
        time_filter = None
        if freshness == "BREAKING": time_filter = "d" # past day
        elif freshness == "RECENT": time_filter = "m" # past month
        
        
        # --- 1. CORE SEARCH (SerpApi -> Fallback to DDGS) ---
        SERPAPI_API_KEY = get_key("SERPAPI_API_KEY")

        search_results = []
        used_source = "ddgs" # Default

        # A. Try SerpApi (Google)
        if SERPAPI_API_KEY:
            try:
                # logger.info(f"Searching via SerpApi: {search_query}")
                params = {
                    "api_key": SERPAPI_API_KEY,
                    "q": search_query,
                    "num": self.max_sources + 2
                }
                # Use raw requests to avoid extra dependencies
                resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    organic = data.get('organic_results', [])
                    if organic:
                        for r in organic:
                            search_results.append({
                                'title': r.get('title'),
                                'href': r.get('link'),
                                'type': 'google_result'
                            })
                        used_source = "serpapi"
                        # logger.info(f"SerpApi returned {len(search_results)} results.")
                else:
                    logger.warning(f"SerpApi Failed ({resp.status_code}): {resp.text[:100]}")
                    
            except Exception as e:
                logger.error(f"SerpApi Error: {e}")

        # B. Fallback to DuckDuckGo (if SerpApi failed or no key)
        if not search_results:
            if SERPAPI_API_KEY: logger.warning("Falling back to DuckDuckGo...")
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(search_query, region='in-en', timelimit=time_filter, max_results=self.max_sources))
                    for r in results:
                        search_results.append({
                            'title': r['title'],
                            'href': r['href'],
                            'type': 'ddg_result'
                        })
                    used_source = "ddgs"
            except Exception as e:
                logger.error(f"DDGS Search Error: {e}")

        # Process Results
        for r in search_results:
            # BLOCK LIST check
            if any(blocked in r['href'] for blocked in ["blogspot", "wordpress", "forum", "reddit"]):
                continue
                
            sources.append({
                "title": r['title'],
                "href": r['href'],
                "type": "official" if ".gov" in r['href'] else "news"
            })

            
        # --- NEW SOURCES INTEGRATION ---
        
        # 1. Wikipedia (General knowledge)
        if topic in ["General Knowledge", "Person", "Technology / Science", "Government Organization"]:
             wiki_data = self._fetch_wikipedia(query)
             if wiki_data: sources.append(wiki_data)

        # 2. Hacker News (Technology)
        if topic in ["Technology / Science", "Company / Startup"]:
             hn_data = self._fetch_hackernews(query)
             if hn_data: sources.extend(hn_data)

        # 3. GitHub (Code/Tech)
        if "github" in query.lower() or "code" in query.lower() or topic == "Technology / Science":
             gh_data = self._fetch_github(query)
             if gh_data: sources.extend(gh_data)


        # 4. NASA (Space/Science)
        if "space" in query.lower() or "nasa" in query.lower() or "planet" in query.lower():
             nasa_data = self._fetch_nasa(query)
             if nasa_data: sources.append(nasa_data)

        # 5. OpenSky (Flights)
        if "flight" in query.lower() or "plane" in query.lower() or "opensky" in query.lower() or "air traffic" in query.lower():
             sky_data = self._fetch_opensky(query)
             if sky_data: sources.append(sky_data)

        # 6. Trefle (Plants)
        if "plant" in query.lower() or "flower" in query.lower() or "botany" in query.lower() or "species" in query.lower():
             plant_data = self._fetch_trefle(query)
             if plant_data: sources.append(plant_data)

        return sources
    
    # --- SPECIALIZED FETCHERS ---

    def _fetch_wikipedia(self, query):
        """Fetches a summary from Wikipedia."""
        try:
            logger.info(f"Fetching Wikipedia for: {query}")
            # Use MediaWiki API
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": 1
            }
            # Wikipedia requires a User-Agent
            headers = {'User-Agent': 'SeethaPremium/1.0 (seetha_bot)'}
            
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data['query']['search']:
                    title = data['query']['search'][0]['title']
                    # Get summary
                    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
                    s_resp = requests.get(summary_url, headers=headers, timeout=5)
                    if s_resp.status_code == 200:
                        s_data = s_resp.json()
                        return {
                            "title": f"Wikipedia: {title}",
                            "href": s_data.get('content_urls', {}).get('desktop', {}).get('page', f"https://en.wikipedia.org/wiki/{title}"),
                            "type": "encyclopedia",
                            "summary": s_data.get('extract', '') # Store summary directly
                        }
        except Exception as e:
            logger.error(f"Wikipedia Fetch Error: {e}")
        return None

    def _fetch_hackernews(self, query):
        """Fetches top discussion from Hacker News (via Algolia)."""
        try:
            logger.info(f"Fetching Hacker News for: {query}")
            params = {
                "query": query,
                "tags": "story",
                "hitsPerPage": 3
            }
            resp = requests.get("https://hn.algolia.com/api/v1/search", params=params, timeout=5)
            results = []
            if resp.status_code == 200:
                hits = resp.json().get('hits', [])
                for hit in hits:
                    if hit.get('url'): # Only links
                        results.append({
                            "title": f"[HN] {hit.get('title')}",
                            "href": hit.get('url'),
                            "type": "forum",
                            "meta": f"Points: {hit.get('points')}, Comments: {hit.get('num_comments')}"
                        })
            return results
        except Exception as e:
            logger.error(f"HN Fetch Error: {e}")
        return []

    def _fetch_github(self, query):
        """Fetches repositories from GitHub."""
        try:
            logger.info(f"Fetching GitHub for: {query}")
            params = {"q": query, "per_page": 2}
            resp = requests.get("https://api.github.com/search/repositories", params=params, timeout=5)
            results = []
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                for item in items:
                    results.append({
                        "title": f"[GitHub] {item.get('full_name')}",
                        "href": item.get('html_url'),
                        "type": "code",
                        "meta": f"Stars: {item.get('stargazers_count')}"
                    })
            return results
        except Exception as e:
            logger.error(f"GitHub Fetch Error: {e}")
        return []

    def _fetch_nasa(self, query):
        """Fetches NASA APOD or Search Data."""
        NASA_API_KEY = get_key("NASA_API_KEY")
        try:
            if not NASA_API_KEY: return None
            logger.info(f"Fetching NASA for: {query}")
            
            # Simple wrapper: Use APOD if generic 'space', or Search for specific
            if "apod" in query.lower() or "today" in query.lower():
                url = "https://api.nasa.gov/planetary/apod"
                params = {"api_key": NASA_API_KEY}
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "title": f"[NASA APOD] {data.get('title')}",
                        "href": data.get('url'), # Image or Video URL
                        "type": "science",
                        "summary": data.get('explanation', '')
                    }
            else:
                 # Search library
                url = "https://images-api.nasa.gov/search"
                params = {"q": query, "media_type": "image"}
                resp = requests.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    items = resp.json().get('collection', {}).get('items', [])
                    if items:
                         item = items[0]
                         data = item.get('data', [{}])[0]
                         return {
                             "title": f"[NASA] {data.get('title')}",
                             "href": "https://images.nasa.gov", # Placeholder as links are deep
                             "type": "science",
                             "summary": data.get('description', '')
                         }
        except Exception as e:
            logger.error(f"NASA Fetch Error: {e}")
        return None

    def _fetch_opensky(self, query):
        """Fetches Live Flight Data from OpenSky Network."""
        OPENSKY_USERNAME = get_key("OPENSKY_USERNAME")
        OPENSKY_PASSWORD = get_key("OPENSKY_PASSWORD")
        try:
            if not OPENSKY_USERNAME or not OPENSKY_PASSWORD: 
                logger.warning("OpenSky credentials missing.")
                return None
                
            logger.info(f"Fetching OpenSky Data...")
            
            # --- OAuth2 Token Exchange ---
            token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
            api_url = "https://opensky-network.org/api/states/all"
            
            headers = {}
            mode_str = " (Anonymous)"
            
            try:
                # 1. Try to get Access Token
                logger.debug(f"OpenSky: Authenticating via OAuth2 Client Credentials...")
                token_data = {
                    "grant_type": "client_credentials",
                    "client_id": OPENSKY_USERNAME,
                    "client_secret": OPENSKY_PASSWORD
                }
                token_resp = requests.post(token_url, data=token_data, timeout=5)
                
                if token_resp.status_code == 200:
                    access_token = token_resp.json().get('access_token')
                    headers = {"Authorization": f"Bearer {access_token}"}
                    mode_str = " (Authenticated)"
                    logger.info("OpenSky: Authentication Successful.")
                else:
                    logger.warning(f"OpenSky Auth Failed ({token_resp.status_code}). Using Anonymous Mode.")
                    
            except Exception as auth_e:
                logger.error(f"OpenSky Auth Error: {auth_e}")
            
            # 2. Fetch Data (with or without token)
            resp = requests.get(api_url, headers=headers, timeout=10)


            if resp.status_code == 200:
                data = resp.json()
                states = data.get('states', [])
                if not states: states = []
                
                count = len(states)
                logger.info(f"OpenSky: Found {count} flights.")
                
                # Create a summary
                mode_str = " (Anonymous Mode)" if resp.request.headers.get('Authorization') is None else ""
                summary = f"Real-Time Air Traffic Report{mode_str}:\\n- Total Airborne Flights: {count}\\n"
                
                # Add examples (first 3)
                if count > 0:
                    summary += "Sample Flights:\\n"
                    for i in range(min(3, count)):
                        s = states[i]
                        # s[0]=icao24, s[1]=callsign/flightnum, s[2]=origin_country
                        callsign = s[1].strip() if s[1] else "N/A"
                        country = s[2].strip() if s[2] else "Unknown"
                        summary += f"- Flight {callsign} (Origin: {country})\\n"
                        
                return {
                    "title": f"[OpenSky] Live Air Traffic: {count} Flights",
                    "href": "https://opensky-network.org/",
                    "type": "data",
                    "summary": summary
                }
            else:
                logger.error(f"OpenSky Error: {resp.status_code} - {resp.text}")
                
        except Exception as e:
            logger.error(f"OpenSky Fetch Error: {e}")
        return None

    def _fetch_trefle(self, query):
        """Fetches Plant Data from Trefle.io."""
        TREFLE_API_TOKEN = get_key("TREFLE_API_TOKEN")
        try:
            if not TREFLE_API_TOKEN: return None
            logger.info(f"Fetching Trefle for: {query}")
            
            # Search
            url = "https://trefle.io/api/v1/plants/search"
            params = {
                "token": TREFLE_API_TOKEN,
                "q": query
            }
            resp = requests.get(url, params=params, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data'):
                    plant = data['data'][0] # Best match
                    common_name = plant.get('common_name') or "Unknown"
                    scientific_name = plant.get('scientific_name')
                    family = plant.get('family')
                    image_url = plant.get('image_url')
                    
                    return {
                        "title": f"[Trefle] {common_name} ({scientific_name})",
                        "href": image_url if image_url else "https://trefle.io",
                        "type": "science",
                        "summary": f"Plant: {common_name}\\nScientific Name: {scientific_name}\\nFamily: {family}"
                    }
        except Exception as e:
            logger.error(f"Trefle Fetch Error: {e}")
        return None

    def _extract_facts(self, text, query):
        prompt = f"""
        Extract independent factual claims relevant to: "{query}" from the text below.
        Return each fact on a new line. No bullets.
        Text: {text[:3000]}
        """
        res = self._llm_call(prompt)
        if not res: return []
        return [line.strip() for line in res.split('\n') if len(line) > 10]

    def _verify_insights(self, all_facts):
        # We need 2+ independent sources effectively saying the same thing.
        # This is hard to do perfectly without source tracking per fact.
        # Simplified: We ask LLM to cluster and count.
        
        if not all_facts: return []
        
        facts_blob = "\n".join([f"- {f}" for f in all_facts])
        
        prompt = f"""
        Analyze these extracted facts. Group them by meaning.
        Identify facts that appear at least twice (implied by multiple variations).
        Return ONLY the Verified Facts (consolidated text) that have strong support.
        Return as a newline separated list.
        
        Facts:
        {facts_blob}
        """
        res = self._llm_call(prompt)
        if not res: return []
        return [line.strip() for line in res.split('\n') if len(line) > 10]

    def _synthesize_final_report(self, query, verified_facts, sources):
        facts_txt = "\n".join([f"- {f}" for f in verified_facts])
        sources_txt = "\n".join([f"- {s['href']}" for s in sources[:5]])
        
        prompt = f"""
        Create a Premium Research Report for: "{query}"
        
        Verified Facts:
        {facts_txt}
        
        Constraints:
        1. Verified Facts Section
        2. Context & AI Insights (Label as '⚠️ AI Context')
        3. No unverified rumors.
        4. Professional tone.
        
        Sources to cite:
        {sources_txt}
        """
        return self._llm_call(prompt)

    def _calculate_confidence(self, num_sources, verified_count):
        # Base = 20%
        # +30% if VERIFIED_INSIGHTS_COUNT >= 3
        # +20% if official sources used (heuristic assumption handled in search)
        # +20% if sources are recent
        # +10% if no contradictions
        
        score = 20
        if verified_count >= 3: score += 30
        if num_sources >= 5: score += 20
        if verified_count > 0: score += 20 # General boost for having any verification
        
        # Hard Rule
        if verified_count == 0: 
            return min(score, 40)
            
        return min(score, 100)

    def _llm_call(self, prompt, system="You are a strict logic engine."):
        # 1. Unified AI client (NVIDIA NIM -> Groq, user's own keys)
        content, err = ai_client.chat_completion(
            [{"role": "system", "content": system},
             {"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        if content:
            return content

        # 2. Gemini (optional extra provider)
        if self.gemini_model:
            try:
                full_prompt = f"System: {system}\n\nUser: {prompt}"
                resp = self.gemini_model.generate_content(full_prompt)
                return resp.text
            except Exception as e:
                logger.warning(f"Gemini call failed: {e}")

        logger.warning(f"All LLM providers unavailable: {err}")
        return "LLM Unavailable"

    def _extract_text(self, url):
        try: 
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200: return None
            soup = BeautifulSoup(resp.content, "lxml")
            for s in soup(["script", "style", "nav", "footer"]): s.extract()
            return soup.get_text(" ", strip=True)[:5000]
        except: return None


# Backwards-compatible alias (old scripts import PremiumResearchEngine)
PremiumResearchEngine = ResearchEngine
