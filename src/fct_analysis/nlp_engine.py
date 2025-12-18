"""Enhanced NLP Engine with rule-based classification and LLM fallback.

This module implements a hybrid approach:
1. Fast keyword/pattern matching for common cases (80%+ coverage)
2. LLM fallback only for ambiguous or complex summaries
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from loguru import logger

# Import LLM functionality for fallback
try:
    from .llm import safe_llm_classify, extract_entities_with_ollama
    from lib.config import Config
except ImportError:
    logger.warning("LLM module not available, using rule-based only")
    safe_llm_classify = None
    extract_entities_with_ollama = None
    Config = None


# Enhanced regex patterns for better accuracy
class PatternLibrary:
    """Comprehensive pattern library for legal document classification."""
    
    # Case Type Patterns
    MANDAMUS_PATTERNS = [
        r'\bmandamus\b',
        r'\bcompels?\b', 
        r'\bunreasonable delay\b',
        r'\bdelay.*unreasonable\b',
        r'\bfailure.*process\b',
        r'\bexpedite\b',
        r'\bspeed up\b',
        r'\btimely.*decision\b',
    ]
    
    JUDICIAL_REVIEW_PATTERNS = [
        r'\bjudicial review\b',
        r'\bjr\b',
        r'\bjudicial review\b',
        r'\breview.*decision\b',
        r'\bapplication.*review\b',
    ]
    
    # Outcome Patterns (with priority)
    DISCONTINUED_PATTERNS = [
        r'notice of discontinuance',
        r'\bdiscontinued\b',
        r'\bwithdrawn\b',
        r'\bwithdraw\b',
        r'application.*discontinued',
        r'applicant.*withdrawn',
    ]
    
    GRANTED_PATTERNS = [
        r'\bgranted\b.*(application|appeal|petition|leave|judicial review)',
        r'(application|appeal|petition|leave|judicial review).*\bgranted\b',
        r'\ballowed\b.*(application|appeal|petition|leave|judicial review)',
        r'\bapproved\b',
        r'\bsuccessful\b',
        r'\bfavorable\b',
        r'\ballow.*appeal\b',
    ]
    
    DISMISSED_PATTERNS = [
        r'\bdismiss(ed|ing)?\b.*(application|appeal|petition|leave|judicial review)',
        r'(application|appeal|petition|leave|judicial review).*\bdismiss(ed|ing)?\b',
        r'\bdenied?\b',
        r'\breject(ed|ing)?\b.*(application|appeal|petition|leave|judicial review)',
        r'\brefused?\b.*(application|appeal|petition|leave|judicial review)',
        r'\bunsuccessful\b',
    ]
    
    MOOT_PATTERNS = [
        r'\bmoot\b',
        r'\bacademic\b',
        r'\bno longer.*relevant\b',
        r'\bresolved.*outside\b',
        r'\bsettled.*outside\b',
    ]
    
    PENDING_PATTERNS = [
        r'\bpending\b',
        r'\bawaiting\b',
        r'\bno decision\b',
        r'\bno result\b',
        r'\bto be determined\b',
        r'\bunder consideration\b',
    ]
    
    # Procedural Event Patterns
    HEARING_PATTERNS = [
        r'\bhearing.*scheduled\b',
        r'\bhearing.*set\b',
        r'\blist.*hearing\b',
        r'\boral.*hearing\b',
        r'\bto.*be.*heard\b',
    ]
    
    NO_HEARING_PATTERNS = [
        r'\bno hearing\b',
        r'\bon the record\b',
        r'\bwithout.*appearance\b',
        r'\bwritten.*submission\b',
        r'\bwithout.*hearing\b',
    ]
    
    MOTION_PATTERNS = [
        r'\bmotion\b',
        r'\bapplication\b',
        r'\binterlocutory\b',
        r'\binterim\b',
    ]
    
    # Visa Office Patterns (for entity extraction)
    VISA_OFFICE_PATTERNS = {
        'beijing': r'\bbeijing\b',
        'new delhi': r'\bnew delhi\b|\bdelhi\b',
        'ankara': r'\bankara\b',
        'islamabad': r'\bislamabad\b',
        'manila': r'\bmanila\b',
        'singapore': r'\bsingapore\b',
        'kuala lumpur': r'\bkuala lumpur\b',
        'hong kong': r'\bhong kong\b',
        'tokyo': r'\btokyo\b',
        'seoul': r'\bseoul\b',
        'bangkok': r'\bbangkok\b',
        'taipei': r'\btaipei\b',
        'ho chi minh': r'\bho chi minh\b|bsaigon\b',
        'jakarta': r'\bjakarta\b',
        'abu dhabi': r'\babu dhabi\b',
        'dubai': r'\bdubai\b',
        'riyadh': r'\briyadh\b',
        'cairo': r'\bcairo\b',
        'nairobi': r'\bnairobi\b',
        'moscow': r'\bmoscow\b',
        'warsaw': r'\bwarsaw\b',
    }
    
    # Judge Pattern
    JUDGE_PATTERNS = [
        r'Justice\s+((?:[A-Z][a-z]+)(?:\s+(?!Language|Matter|Court|Order|Decision|dated|at\b)[A-Z][a-z]+)*)\b',
        r'Judge\s+((?:[A-Z][a-z]+)(?:\s+(?!Language|Matter|Court|Order|Decision|dated|at\b)[A-Z][a-z]+)*)\b',
        r'by\s+((?:[A-Z][a-z]+)(?:\s+(?!Language|Matter|Court|Order|Decision|dated|at\b)[A-Z][a-z]+)*)\s+A\.?J\.?\b',
        r'((?:[A-Z][a-z]+)(?:\s+(?!Language|Matter|Court|Order|Decision|dated|at\b)[A-Z][a-z]+)*)\s+J\.?\b',
    ]


class EnhancedNLPEngine:
    """Enhanced NLP engine with pattern matching and LLM fallback."""
    
    def __init__(self, use_llm_fallback: bool = True, llm_timeout: int | None = None, 
                 wait_for_ollama: bool = True, ollama_wait_time: int = 120):
        self.use_llm_fallback = use_llm_fallback and extract_entities_with_ollama is not None
        self.wait_for_ollama = wait_for_ollama
        self.ollama_wait_time = ollama_wait_time
        
        if Config:
            self.llm_timeout = llm_timeout or Config.get_ollama_timeout()
        else:
            self.llm_timeout = llm_timeout if llm_timeout is not None else 30  # Fallback timeout
        self.pattern_lib = PatternLibrary()
        
        # Compile regex patterns for efficiency
        self._compile_patterns()
        
    def _compile_patterns(self):
        """Pre-compile all regex patterns for better performance."""
        self.compiled_patterns = {}
        
        for attr_name in dir(self.pattern_lib):
            if not attr_name.endswith('_PATTERNS'):
                continue
                
            patterns = getattr(self.pattern_lib, attr_name)
            
            # Use case-sensitive matching ONLY for judges (Capitalized Names)
            flags = re.IGNORECASE
            if attr_name == 'JUDGE_PATTERNS':
                flags = 0  # Case sensitive
            
            if isinstance(patterns, dict):
                self.compiled_patterns[attr_name] = {
                    key: re.compile(pattern, flags) 
                    for key, pattern in patterns.items()
                }
            else:
                self.compiled_patterns[attr_name] = [
                    re.compile(pattern, flags) 
                    for pattern in patterns
                ]
    
    def _extract_text(self, case_obj: Any) -> str:
        """Extract and combine relevant text from case object, with contextual labels."""
        parts = []
        
        if isinstance(case_obj, dict):
            # 1. Header Information (Style of cause, Title, Nature of proceeding)
            for field in ["style_of_cause", "title", "nature_of_proceeding"]:
                value = case_obj.get(field, "")
                if value:
                    parts.append(f"[HEADER] {value}")
            
            # 2. Docket entries
            docket_entries = case_obj.get("docket_entries") or []
            if docket_entries:
                # First entries
                first_entries = docket_entries[:3]
                for de in first_entries:
                    summary = de.get("summary", "") or de.get("recorded_entry_summary", "")
                    if summary:
                        parts.append(f"[START] {summary}")
                
                # Priority Entries
                priority_keywords = ["(Final decision)", "discontinuance", "discontinued", "withdrawn", "dismissing", "dismissed"]
                priority_entries = []
                for de in docket_entries:
                    summary = (de.get("summary", "") or de.get("recorded_entry_summary", "")).lower()
                    if any(kw.lower() in summary for kw in priority_keywords):
                        priority_entries.append(de)
                
                for de in priority_entries:
                    summary = de.get("summary", "") or de.get("recorded_entry_summary", "")
                    if summary:
                        parts.append(f"[PRIORITY] {summary}")
                
                # Recent entries
                last_entries = docket_entries[-10:]
                for de in last_entries:
                    # Skip if already added to minimize noise
                    if de in first_entries or de in priority_entries:
                        continue
                    summary = de.get("summary", "") or de.get("recorded_entry_summary", "")
                    if summary:
                        parts.append(f"[END] {summary}")
        else:
            # Handle pandas series
            parts.append(f"[HEADER] {str(case_obj.get('style_of_cause', ''))}")
            parts.append(f"[HEADER] {str(case_obj.get('title', ''))}")
            
        return "\n".join([p.strip() for p in parts if p.strip()])
    
    def _extract_full_json(self, case_obj: Any) -> str:
        """Extract optimized JSON data for LLM analysis, focusing on start and end of case."""
        import json
        
        def make_serializable(obj):
            """Make object JSON serializable."""
            if isinstance(obj, list):
                return [make_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    if value is None:
                        result[key] = None
                    elif hasattr(value, 'isoformat'):
                        result[key] = value.isoformat()
                    elif isinstance(value, (list, dict)):
                        result[key] = make_serializable(value)
                    else:
                        result[key] = value
                return result
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                return obj
        
        # Optimize Case Object: Filter docket entries to reduce tokens
        optimized_case = {}
        if isinstance(case_obj, dict):
            for k, v in case_obj.items():
                if k != "docket_entries":
                    optimized_case[k] = v
            
            docket_entries = case_obj.get("docket_entries") or []
            if docket_entries:
                # Include first 3, last 10, and all priority entries
                selected_entries = []
                seen_indices = set()
                
                # First 3
                for i in range(min(len(docket_entries), 3)):
                    selected_entries.append(docket_entries[i])
                    seen_indices.add(i)
                
                # Priority Entries
                priority_keywords = ["(Final decision)", "discontinuance", "discontinued", "withdrawn", "dismissing", "dismissed"]
                for i, de in enumerate(docket_entries):
                    summary = (de.get("summary", "") or de.get("recorded_entry_summary", "")).lower()
                    if any(kw.lower() in summary for kw in priority_keywords) and i not in seen_indices:
                        selected_entries.append(de)
                        seen_indices.add(i)
                
                # Last 10
                start_last = max(0, len(docket_entries) - 10)
                for i in range(start_last, len(docket_entries)):
                    if i not in seen_indices:
                        selected_entries.append(docket_entries[i])
                        seen_indices.add(i)
                
                optimized_case["docket_entries"] = selected_entries
                optimized_case["total_docket_count"] = len(docket_entries)
        else:
            optimized_case = case_obj
            
        # Create a serializable copy
        serializable_case = make_serializable(optimized_case)
        
        # Convert to JSON
        case_json = json.dumps(serializable_case, indent=2, ensure_ascii=False)
        
        prompt = f"""You are a legal text classifier for Canadian Federal Court cases.

Analyze the following case data (optimized to show relevant start/end entries) and identify:

1. Whether this is a Mandamus case ("Mandamus" or "Other").
2. The **FINAL** outcome of the case (ignore interlocutory orders):
   - dismissed
   - allowed  
   - discontinued
   - moot
   - pending / no result
   
   ⚠️ CRITICAL: 
   - If an "Application for leave" is GRANTED, it just means the case goes to hearing. 
   - If the subsequent "judicial review" is DISMISSED, the valid status is **DISMISSED**.
   - Look for entries marked "(Final decision)" or the very last entry in the list.
   
3. The nature of the matter (Mandamus, JR, Appeal, Motion, Leave, etc.)
4. Whether a hearing was held or scheduled.
5. The visa office (if mentioned)
6. The judge name (Focus on the judge who made the FINAL decision)

Case Data (Total entries: {len(docket_entries) if 'docket_entries' in locals() else 'unknown'}):
{case_json}

Return ONLY valid JSON:
{{
  "case_type": "Mandamus" or "Other",
  "status": "Dismissed" or "Allowed" or "Discontinued" or "Moot" or "Pending" or "Ongoing",
  "visa_office": "city name or null",
  "judge": "judge name or null", 
  "has_hearing": true/false,
  "confidence": "high" or "medium" or "low",
  "nature": "string (Mandamus, JR, Appeal, Motion, Leave, etc.)"
}}"""
        return prompt
    
    def _match_patterns(self, text: str, pattern_list: list) -> bool:
        """Check if any pattern in the list matches the text."""
        for pattern in pattern_list:
            if pattern.search(text):
                return True
        return False
    
    def _extract_visa_office(self, text: str) -> Optional[str]:
        """Extract visa office from text using patterns."""
        for office, pattern in self.compiled_patterns['VISA_OFFICE_PATTERNS'].items():
            if pattern.search(text):
                office_name = office.title() if office.lower() != 'new delhi' else 'New Delhi'
                # Limit length to prevent database errors
                return office_name[:200] if len(office_name) > 200 else office_name
        return None
    
    def _extract_judge(self, text: str) -> Optional[str]:
        """Extract judge name from text using patterns. Returns the LAST judge mentioned."""
        all_matches = []
        for pattern in self.compiled_patterns['JUDGE_PATTERNS']:
            # Find all matches in the text
            matches = pattern.findall(text)
            all_matches.extend(matches)
            
        if all_matches:
            # Return the last judge mentioned (usually associated with final decision)
            judge_name = all_matches[-1]
            # Limit length to prevent database errors
            return judge_name[:200] if len(judge_name) > 200 else judge_name
            
        return None
    
    def _is_ambiguous(self, text: str, initial_result: Dict) -> bool:
        """Determine if the initial classification is ambiguous and needs LLM verification."""
        
        # Be more conservative about LLM usage - only trigger for clear conflicts
        # With the new priority order (Discontinued > Moot > Dismissed > Granted), 
        # we only need to check for actual contradictions
        conflict_indicators = [
            (self._match_patterns(text, self.compiled_patterns['GRANTED_PATTERNS']) and 
             initial_result.get('status') == 'Dismissed'),
            (self._match_patterns(text, self.compiled_patterns['DISMISSED_PATTERNS']) and 
             initial_result.get('status') == 'Granted'),
            (self._match_patterns(text, self.compiled_patterns['DISCONTINUED_PATTERNS']) and 
             initial_result.get('status') in ['Granted', 'Dismissed', 'Moot']),
            (self._match_patterns(text, self.compiled_patterns['MOOT_PATTERNS']) and 
             initial_result.get('status') in ['Granted', 'Dismissed']),
        ]
        
        # Only trigger LLM for actual conflicts, not complex language
        if any(conflict_indicators):
            logger.debug(f"Conflict detected - triggering LLM")
            return True
        
        # Additional check: if text contains conflicting outcome phrases
        has_granted = self._match_patterns(text, self.compiled_patterns['GRANTED_PATTERNS'])
        has_dismissed = self._match_patterns(text, self.compiled_patterns['DISMISSED_PATTERNS'])
        has_discontinued = self._match_patterns(text, self.compiled_patterns['DISCONTINUED_PATTERNS'])
        has_moot = self._match_patterns(text, self.compiled_patterns['MOOT_PATTERNS'])
        
        # Trigger LLM for multiple conflicting outcomes
        outcome_count = sum([has_granted, has_dismissed, has_discontinued, has_moot])
        if outcome_count > 1:
            # Discontinued almost always takes priority and is high confidence in Rule-based
            if has_discontinued and initial_result.get('status') == 'Discontinued':
                return False
            logger.debug(f"Multiple conflicting outcomes detected ({outcome_count}) - triggering LLM")
            return True
        
        # Skip LLM for complex but clear cases - use enhanced rules instead
        return False
    
    def _llm_fallback(self, text: str, case_obj: Any) -> Dict:
        """Use LLM for complex/ambiguous cases with enterprise-grade safety."""
        if not self.use_llm_fallback:
            logger.debug("LLM fallback disabled, using rule-based result")
            return {}
        
        if safe_llm_classify is None:
            logger.warning("Safe LLM classification not available")
            return {}
        
        try:
            # Extract summary text for classification
            summary_text = text if text else self._extract_summary_text(case_obj)
            
            # Get model from config
            model = None
            if Config:
                model = Config.get_ollama_model()
                if not model:
                    model = "gemma2:2b"  # Default small model for CPU-only (available)
            else:
                model = "gemma2:2b"
            
            logger.info(f"🤖 Safe LLM Analysis - Model: {model}")
            logger.info(f"📝 Summary text preview: {summary_text[:200]}...")
            
            logger.debug("🚀 Sending safe request to LLM...")
            import time
            start_time = time.time()
            
            # Use the safe classification function
            result = safe_llm_classify(summary_text, model=model, 
                                     wait_for_idle=self.wait_for_ollama, 
                                     max_idle_wait=self.ollama_wait_time)
            
            # Calculate and log processing time
            elapsed_time = time.time() - start_time
            logger.info(f"⏱️ Safe LLM processing completed in {elapsed_time:.2f}s")
            
            # Parse and validate LLM response
            if result:
                logger.info(f"✅ Safe LLM fallback successful")
                logger.debug(f"📊 Raw LLM result: {result}")
                normalized = self._normalize_safe_llm_result(result)
                logger.info(f"🔍 Normalized result: {normalized}")
                return normalized
            else:
                logger.warning("❌ Safe LLM returned empty result")
                
        except Exception as e:
            logger.error(f"💥 Safe LLM fallback failed: {e}")
            logger.info(f"🔄 LLM service unavailable, using rule-based analysis instead")
            logger.exception("Full exception details:")
        
        # Return empty dict to fallback to rule-based analysis
        return {}
    
    def _normalize_llm_result(self, llm_result: Dict) -> Dict:
        """Normalize LLM result to match expected format."""
        normalized = {}
        
        # Map case type
        case_type = str(llm_result.get('case_type', '')).lower()
        if 'mandamus' in case_type:
            normalized['type'] = 'Mandamus'
        else:
            normalized['type'] = 'Other'
        
        # Map status with enhanced options
        status = str(llm_result.get('status', '')).lower()
        if 'discontinu' in status or 'withdrawn' in status:
            normalized['status'] = 'Discontinued'
        elif 'allow' in status or 'grant' in status or 'approv' in status:
            normalized['status'] = 'Granted'
        elif 'dismiss' in status or 'denied' in status or 'deny' in status:
            normalized['status'] = 'Dismissed'
        elif 'moot' in status:
            normalized['status'] = 'Moot'
        elif 'pending' in status or 'ongoing' in status or 'no result' in status:
            normalized['status'] = 'Ongoing'
        else:
            normalized['status'] = 'Ongoing'
        
        # Extract entities with length limits
        if llm_result.get('visa_office') and str(llm_result['visa_office']).lower() != 'null':
            visa_office = str(llm_result['visa_office'])
            normalized['visa_office'] = visa_office[:200] if len(visa_office) > 200 else visa_office
        if llm_result.get('judge') and str(llm_result['judge']).lower() != 'null':
            judge = str(llm_result['judge'])
            normalized['judge'] = judge[:200] if len(judge) > 200 else judge
        
        # Map boolean hearing field
        has_hearing = llm_result.get('has_hearing')
        if isinstance(has_hearing, bool):
            normalized['has_hearing'] = has_hearing
        elif isinstance(has_hearing, str):
            normalized['has_hearing'] = has_hearing.lower() in ['true', 'yes', '1']
        else:
            normalized['has_hearing'] = False
        
        # Add nature of matter if provided
        if llm_result.get('nature') and str(llm_result['nature']).lower() != 'null':
            nature = str(llm_result['nature'])
            normalized['nature'] = nature[:100] if len(nature) > 100 else nature
        
        # Ensure values are strings or None, and filter out None values
        for key in ['visa_office', 'judge', 'nature']:
            if key in normalized:
                value = normalized[key]
                if value is not None and value != 'null':
                    normalized[key] = str(value)
                else:
                    normalized[key] = None
        
        # Confidence
        normalized['llm_confidence'] = llm_result.get('confidence', 'medium')
        
        return normalized
    
    def _normalize_safe_llm_result(self, llm_result: Dict) -> Dict:
        """Normalize safe LLM result to match expected format."""
        normalized = {}
        
        # Map is_mandamus to type
        is_mandamus = llm_result.get('is_mandamus')
        if isinstance(is_mandamus, bool):
            normalized['type'] = 'Mandamus' if is_mandamus else 'Other'
        elif isinstance(is_mandamus, str):
            normalized['type'] = 'Mandamus' if is_mandamus.lower() in ['true', 'yes', '1'] else 'Other'
        else:
            normalized['type'] = 'Other'
        
        # Map outcome to status
        outcome = str(llm_result.get('outcome', '')).lower()
        if 'discontinu' in outcome or 'withdrawn' in outcome:
            normalized['status'] = 'Discontinued'
        elif 'grant' in outcome or 'allow' in outcome or 'approv' in outcome:
            normalized['status'] = 'Granted'
        elif 'dismiss' in outcome or 'denied' in outcome or 'deny' in outcome:
            normalized['status'] = 'Dismissed'
        elif 'moot' in outcome:
            normalized['status'] = 'Moot'
        elif 'pending' in outcome or 'ongoing' in outcome or 'no result' in outcome:
            normalized['status'] = 'Ongoing'
        else:
            normalized['status'] = 'Ongoing'
        
        # Map nature field
        nature = llm_result.get('nature')
        if nature and str(nature).lower() != 'null':
            normalized['nature'] = str(nature)[:100]
        
        # Map has_hearing field
        has_hearing = llm_result.get('has_hearing')
        if isinstance(has_hearing, bool):
            normalized['has_hearing'] = has_hearing
        elif isinstance(has_hearing, str):
            normalized['has_hearing'] = has_hearing.lower() in ['true', 'yes', '1']
        else:
            normalized['has_hearing'] = False
        
        # Set confidence based on model type
        normalized['llm_confidence'] = 'high' if normalized['type'] == 'Mandamus' else 'medium'
        
        return normalized
    
    def _extract_summary_text(self, case_obj: Any) -> str:
        """Extract optimized summary text for LLM classification, prioritizing start and end."""
        try:
            if hasattr(case_obj, 'docket_entries') and case_obj.docket_entries:
                docket_entries = case_obj.docket_entries
                summary_parts = []
                
                # First 2 entries
                for entry in docket_entries[:2]:
                    desc = getattr(entry, 'description', '') or getattr(entry, 'recorded_entry_summary', '')
                    if desc:
                        summary_parts.append(f"START: {desc}")
                
                # Final decisions
                for entry in docket_entries:
                    desc = getattr(entry, 'description', '') or getattr(entry, 'recorded_entry_summary', '')
                    if desc and "(Final decision)" in desc:
                        summary_parts.append(f"FINAL DECISION: {desc}")
                
                # Last 2 entries
                for entry in docket_entries[-2:]:
                    # Skip if already added
                    desc = getattr(entry, 'description', '') or getattr(entry, 'recorded_entry_summary', '')
                    if desc and not any(desc in p for p in summary_parts):
                        summary_parts.append(f"END: {desc}")
                
                summary = ' | '.join(summary_parts)
                return summary[:1200]
                
            elif hasattr(case_obj, 'title') and case_obj.title:
                return case_obj.title[:500]
            else:
                return str(case_obj)[:500]
        except Exception as e:
            logger.warning(f"Failed to extract summary text: {e}")
            return ""
    
    def classify_case(self, case_obj: Any) -> Dict:
        """
        Classify a case using the hybrid NLP+LLM approach.
        
        Args:
            case_obj: Case object (dict or pandas Series)
            
        Returns:
            Dict with classification results and metadata
        """
        # Extract case identifier for logging
        if isinstance(case_obj, dict):
            case_id = case_obj.get("case_number", "unknown")
        else:
            case_id = getattr(case_obj, "case_number", "unknown")
        
        text = self._extract_text(case_obj)
        
        if not text.strip():
            logger.debug(f"📄 Case {case_id}: Empty text, returning default classification")
            return {
                'type': 'Other',
                'status': 'Ongoing',
                'method': 'empty',
                'confidence': 'low'
            }
        
        logger.debug(f"📄 Case {case_id}: Starting classification (text length: {len(text)} chars)")
        logger.debug(f"📝 Text preview: {text[:150]}...")
        
        # Phase 1: Fast rule-based classification
        result = {
            'type': 'Other',
            'status': 'Ongoing',
            'method': 'rule_based',
            'confidence': 'high'
        }
        
        # Case Type Classification
        if self._match_patterns(text, self.compiled_patterns['MANDAMUS_PATTERNS']):
            result['type'] = 'Mandamus'
            logger.debug(f"🏷️ Case {case_id}: Detected Mandamus patterns")
        else:
            result['type'] = 'Other'
            logger.debug(f"🏷️ Case {case_id}: Classified as Other")
        
        # Enhanced Status Classification with better contextual awareness
        # We create a status-specific text that excludes [HEADER] and [START] for Dismissed/Granted checks
        # to avoid matching keywords that describe the original decision being reviewed
        lines = text.split('\n')
        voters = []
        for line in lines:
            if line.startswith('[HEADER]') or line.startswith('[START]'):
                continue
            
            line_lower = line.lower()
            # Skip interlocutory decisions and specific motion results to avoid false positive status
            if 'interlocutory decision' in line_lower or 'motion in writing' in line_lower:
                continue
            
            # Skip conditional statements and noise
            if 'if leave granted' in line_lower or 'unless otherwise ordered' in line_lower:
                continue
            if 'if the court grants leave' in line_lower or 'if leave is granted' in line_lower:
                continue
                
            voters.append(line)
        status_text = '\n'.join(voters)
        
        # Priority 1: Discontinued / Moot (These are high confidence even if early)
        if self._match_patterns(text, self.compiled_patterns['DISCONTINUED_PATTERNS']):
            result['status'] = 'Discontinued'
            logger.debug(f"📊 Case {case_id}: Status = Discontinued")
        elif self._match_patterns(text, self.compiled_patterns['MOOT_PATTERNS']):
            result['status'] = 'Moot'
            logger.debug(f"📊 Case {case_id}: Status = Moot")
        
        # Priority 2: Dismissed / Granted (Use status_text to avoid false positives from original decision)
        elif self._match_patterns(status_text, self.compiled_patterns['DISMISSED_PATTERNS']):
            result['status'] = 'Dismissed'
            logger.debug(f"📊 Case {case_id}: Status = Dismissed (matched in outcome section)")
        elif self._match_patterns(status_text, self.compiled_patterns['GRANTED_PATTERNS']):
            # Check for negators in the outcome section
            complex_negators = ['however', 'although', 'despite', 'nevertheless']
            has_negator = any(negator in status_text.lower() for negator in complex_negators)
            
            if has_negator and self._match_patterns(status_text, self.compiled_patterns['DISMISSED_PATTERNS']):
                result['status'] = 'Dismissed'
                logger.debug(f"📊 Case {case_id}: Status = Dismissed (complex case with negator in outcome)")
            else:
                result['status'] = 'Granted'
                logger.debug(f"📊 Case {case_id}: Status = Granted")
        
        # Priority 3: Pending / Ongoing
        elif self._match_patterns(text, self.compiled_patterns['PENDING_PATTERNS']):
            result['status'] = 'Ongoing'
            logger.debug(f"📊 Case {case_id}: Status = Ongoing (pending patterns)")
        else:
            result['status'] = 'Ongoing'
            logger.debug(f"📊 Case {case_id}: Status = Ongoing (default)")
        
        # Entity Extraction
        visa_office = self._extract_visa_office(text)
        judge = self._extract_judge(text)
        
        # Post-processing: If case is discontinued, it wasn't decided by the judge who issued interlocutory orders
        if result.get('status') == 'Discontinued':
            judge = None
        has_hearing = (
            self._match_patterns(text, self.compiled_patterns['HEARING_PATTERNS']) and
            not self._match_patterns(text, self.compiled_patterns['NO_HEARING_PATTERNS'])
        )
        
        # Only add keys with valid values to maintain type consistency
        if visa_office is not None:
            result['visa_office'] = visa_office
        if judge is not None:
            result['judge'] = judge
        result['has_hearing'] = bool(has_hearing)
        
        # Log extracted entities
        if result.get('visa_office'):
            logger.debug(f"🌍 Case {case_id}: Visa office = {result['visa_office']}")
        if result.get('judge'):
            logger.debug(f"⚖️ Case {case_id}: Judge = {result['judge']}")
        logger.debug(f"👂 Case {case_id}: Hearing = {result['has_hearing']}")
        
        # Phase 2: Check if LLM verification is needed
        if self._is_ambiguous(text, result):
            logger.info(f"🤔 Case {case_id}: Ambiguous case detected, using LLM fallback")
            logger.info(f"🔄 Case {case_id}: Switching to HYBRID METHOD (Rule + LLM)")
            llm_result = self._llm_fallback(text, case_obj)
            
            if llm_result:
                # Merge LLM results, preferring LLM for ambiguous cases
                original_type = result['type']
                original_status = result['status']
                
                # Special Safety Check: Do not override "Dismissed" or "Discontinued" with "Granted" or "Ongoing" unless LLM is very confident
                # This protects against "Leave Granted -> JR Dismissed" or "Notice of Discontinuance -> Receipt" false positives
                if original_status in ['Dismissed', 'Discontinued'] and llm_result.get('status') in ['Granted', 'Ongoing']:
                    if llm_result.get('llm_confidence') != 'high':
                        logger.warning(f"⚠️ Case {case_id}: LLM suggested '{llm_result.get('status')}' but '{original_status}' rule is preferred (Confidence: {llm_result.get('llm_confidence')})")
                        # Only update non-status fields from LLM
                        llm_result.pop('status', None)
                
                result.update(llm_result)
                result['method'] = 'hybrid'
                result['confidence'] = llm_result.get('llm_confidence', 'medium')
                
                # Log changes made by LLM
                if original_type != result['type']:
                    logger.info(f"🔄 Case {case_id}: Type changed from {original_type} to {result['type']} by LLM")
                if original_status != result['status']:
                    logger.info(f"🔄 Case {case_id}: Status changed from {original_status} to {result['status']} by LLM")
                logger.info(f"✅ Case {case_id}: HYBRID METHOD completed (Rule + LLM)")
                logger.info(f"📈 Case {case_id}: Final result - Type: {result['type']}, Status: {result['status']}, Method: {result['method']}, Confidence: {result['confidence']}")
            else:
                result['confidence'] = 'low'  # Ambiguous but LLM failed
                logger.warning(f"⚠️ Case {case_id}: LLM fallback failed, keeping rule-based with low confidence")
        else:
            # High confidence rule-based result
            logger.debug(f"✅ Case {case_id}: High confidence rule-based classification")
        
        return result
    
    def get_statistics(self) -> Dict:
        """Get classification statistics and performance metrics."""
        # This would be implemented to track classification performance
        # For now, return placeholder
        return {
            'total_classified': 0,
            'rule_based_count': 0,
            'llm_fallback_count': 0,
            'average_confidence': 0.0,
        }


# Global instance for use
_nlp_engine = None

def get_nlp_engine(use_llm_fallback: bool = True, wait_for_ollama: bool = True, ollama_wait_time: int = 120) -> EnhancedNLPEngine:
    """Get or create the global NLP engine instance."""
    global _nlp_engine
    if _nlp_engine is None:
        _nlp_engine = EnhancedNLPEngine(use_llm_fallback=use_llm_fallback, 
                                     wait_for_ollama=wait_for_ollama, 
                                     ollama_wait_time=ollama_wait_time)
    return _nlp_engine

def classify_case_enhanced(case_obj: Any, use_llm_fallback: bool = True, wait_for_ollama: bool = True, ollama_wait_time: int = 120) -> Dict:
    """Convenience function for single case classification."""
    engine = get_nlp_engine(use_llm_fallback, wait_for_ollama, ollama_wait_time)
    return engine.classify_case(case_obj)