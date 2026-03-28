"""
Simulation Configuration Smart Generator
Uses LLM to automatically generate detailed simulation parameters based on requirements, document content, and graph info
Fully automated, no manual parameter setting needed

Uses step-by-step generation strategy to avoid failure from generating too much content at once:
1. Generate time configuration
2. Generate event configuration
3. Generate Agent configuration in batches
4. Generate platform configuration
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.simulation_config')

# China daily schedule configuration (Beijing time)
CHINA_TIMEZONE_CONFIG = {
    # Late night (almost no activity)
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Morning (gradually waking up)
    "morning_hours": [6, 7, 8],
    # Work hours
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Evening peak (most active)
    "peak_hours": [19, 20, 21, 22],
    # Night (activity declining)
    "night_hours": [23],
    # Activity coefficients
    "activity_multipliers": {
        "dead": 0.05,      # Almost no one at dawn
        "morning": 0.4,    # Gradually active in morning
        "work": 0.7,       # Work hoursin等
        "peak": 1.5,       # Evening peak
        "night": 0.5       # Declining at night
    }
}


@dataclass
class AgentActivityConfig:
    """Single Agent activity configuration"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # Activity configuration (0.0-1.0)
    activity_level: float = 0.5  # Overall activity level
    
    # Post frequency (expected posts per hour)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # Active hours (24-hour format, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # Response speed (delay in responding to hot events, unit: simulated minutes)
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # Sentiment bias (-1.0 to 1.0, negative to positive)
    sentiment_bias: float = 0.0
    
    # Stance (attitude toward specific topics)
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # Influence weight (determines probability of posts being seen by other Agents)
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Time simulation configuration (based on Chinese daily schedule)"""
    # Total simulation duration (simulated hours)
    total_simulation_hours: int = 72  # Default: simulate 72 hours (3 days)
    
    # Time per round (simulated minutes) - default 60 minutes (1 hour), faster time flow
    minutes_per_round: int = 60
    
    # Range of Agents activated per hour
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # Peak hours (19-22, most active time in China)
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # Off-peak hours (0-5 AM, almost no activity)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Extremely low activity at dawn
    
    # Morning hours
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # Work hours
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """Event configuration"""
    # Initial events (triggered at simulation start)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)
    
    # Scheduled events (triggered at specific times)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # Hot topic keywords
    hot_topics: List[str] = field(default_factory=list)
    
    # Narrative direction
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Platform-specific configuration"""
    platform: str  # twitter or reddit
    
    # Recommendation algorithm weights
    recency_weight: float = 0.4  # Recency
    popularity_weight: float = 0.3  # Popularity
    relevance_weight: float = 0.3  # Relevance
    
    # Viral threshold (interactions needed to trigger spread)
    viral_threshold: int = 10
    
    # Echo chamber strength (degree of similar opinion clustering)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Complete simulation parameter configuration"""
    # Basic info
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # Time config
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # Agent config list
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # Event config
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # Platform config
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLM config
    llm_model: str = ""
    llm_base_url: str = ""
    
    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM's推理说明
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Simulation Configuration Smart Generator
    
    Uses LLM to analyze simulation requirements, document content, graph entity info,
    automatically generate optimal simulation parameter configuration
    
    Uses step-by-step generation strategy:
    1. Generate time and event configs (lightweight)
    2. Generate Agent configs in batches (10-20 per batch)
    3. Generate platform config
    """
    
    # Maximum context character count
    MAX_CONTEXT_LENGTH = 50000
    # Number of Agents per batch
    AGENTS_PER_BATCH = 15
    
    # Context truncation length for each step (character count)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Time config
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Event config
    ENTITY_SUMMARY_LENGTH = 300          # Entity summary
    AGENT_SUMMARY_LENGTH = 300           # Entity summary in Agent config
    ENTITIES_PER_TYPE_DISPLAY = 20       # Display count per entity type
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None
    ):
        self.provider = provider or Config.LLM_PROVIDER
        # Use orchestration model for config generation (more capable)
        self.model_name = model_name or Config.LLM_ORCHESTRATION_MODEL

        if self.provider == 'anthropic':
            self.api_key = api_key or Config.ANTHROPIC_API_KEY
            self.base_url = base_url or Config.ANTHROPIC_BASE_URL
        else:
            self.api_key = api_key or Config.LLM_API_KEY
            self.base_url = base_url or Config.LLM_BASE_URL

        if not self.api_key:
            raise ValueError("LLM API key is not configured (set LLM_API_KEY or ANTHROPIC_API_KEY)")

        # Use native Anthropic SDK only for direct Anthropic API;
        # for OpenAI-compatible proxies (e.g. cliproxy), use OpenAI SDK
        self._use_anthropic_sdk = (
            self.provider == 'anthropic'
            and self.base_url
            and 'anthropic.com' in self.base_url
        )

        if self._use_anthropic_sdk:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=self.api_key)
            self.client = None
        else:
            from openai import OpenAI
            self._anthropic_client = None
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Smart generation of complete simulation config (step-by-step)
        
        Args:
            simulation_id: Simulation ID
            project_id: Project ID
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            document_text: Original document content
            entities: Filtered entity list
            enable_twitter: Whether to enable Twitter
            enable_reddit: Whether to enable Reddit
            progress_callback: Progress callback (current_step, total_steps, message)
            
        Returns:
            SimulationParameters: Complete simulation parameters
        """
        logger.info(f"Starting smart config generation: simulation_id={simulation_id}, entities={len(entities)}")
        
        # Calculate total steps
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Time config + 事件配置 + N批Agent + 平台配置
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Build base context info
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== Step 1: Generate time config ==========
        report_progress(1, "Generating time configuration...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"时间配置: {time_config_result.get('reasoning', 'Success')}")
        
        # ========== Step 2: Generate event config ==========
        report_progress(2, "Generating event config and hot topics...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"事件配置: {event_config_result.get('reasoning', 'Success')}")
        
        # ========== Steps 3-N: Generate Agent configs in batches ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"生成Agent配置 ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(f"Agent配置: Success生成 {len(all_agent_configs)} 个")
        
        # ========== Assign publisher Agents for initial posts ==========
        logger.info("Assigning suitable publisher Agents for initial posts...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"初始帖子分配: {assigned_count} 个帖子已分配发布者")
        
        # ========== Final step: Generate platform config ==========
        report_progress(total_steps, "Generating platform configuration...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Build final parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"Simulation config generation complete: {len(params.agent_configs)} Agent configs")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Build LLM context, truncated to max length"""
        
        # Entity summary
        entity_summary = self._summarize_entities(entities)
        
        # Build context
        context_parts = [
            f"## Simulation Requirement\n{simulation_requirement}",
            f"\n## Entity Info ({len(entities)} entities)\n{entity_summary}",
        ]
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # 留500字符余量
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(document truncated)"
            context_parts.append(f"\n## Original document content\n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Generate entity summary"""
        lines = []
        
        # Group by type
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)} entities)")
            # Use configured display count and summary length
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... and {len(type_entities) - display_count} more")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM call with retry and JSON fix logic"""
        import re

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                temperature = 0.7 - (attempt * 0.1)  # 每次retry降低温度

                if self._use_anthropic_sdk:
                    json_instruction = "\n\nIMPORTANT: You must respond with valid JSON only, no markdown formatting."
                    response = self._anthropic_client.messages.create(
                        model=self.model_name,
                        system=system_prompt + json_instruction,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=8192,
                    )
                    content = response.content[0].text
                    finish_reason = response.stop_reason
                    # Anthropic uses 'end_turn' for normal, 'max_tokens' for truncation
                    if finish_reason == 'max_tokens':
                        finish_reason = 'length'
                else:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"},
                        temperature=temperature,
                    )
                    content = response.choices[0].message.content
                    finish_reason = response.choices[0].finish_reason
                
                # Check if truncated
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # Try to parse JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # Try to fix JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLM调用Failed")
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON"""
        content = content.strip()
        
        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed strings
        if content and content[-1] not in '",}]':
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Try to fix configuration JSON"""
        import re
        
        # Fix truncation
        content = self._fix_truncated_json(content)
        
        # Extract JSON part
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # Remove newlines from strings
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Try removing all control characters
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Generate time configuration"""
        # Use configured context truncation length
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # Calculate max allowed (90% of agent count)
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""Based on the following simulation requirements, generate a time simulation configuration.

{context_truncated}

## Task
Generate a time configuration JSON.

### General principles (adjust flexibly based on the specific event and participant groups):
- Early morning 0-5: almost no activity (activity factor 0.05)
- Morning 6-8: gradually active (activity factor 0.4)
- Work hours 9-18: moderate activity (activity factor 0.7)
- Evening 19-22: peak period (activity factor 1.5)
- After 23: activity declines (activity factor 0.5)
- Adjust based on participant type: student groups peak later (21-23), media is active all day, government agencies only during work hours
- Breaking news may cause late-night discussion — off_peak_hours can be shortened accordingly

### Return JSON format (no markdown)

Example:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Brief explanation of this time configuration"
}}

Field descriptions:
- total_simulation_hours (int): Total simulation duration, 24-168 hours; shorter for breaking news, longer for sustained topics
- minutes_per_round (int): Duration per round, 30-120 minutes, recommend 60
- agents_per_hour_min (int): Minimum agents activated per hour (range: 1-{max_agents_allowed})
- agents_per_hour_max (int): Maximum agents activated per hour (range: 1-{max_agents_allowed})
- peak_hours (int array): Peak activity hours, adjust based on participant groups
- off_peak_hours (int array): Low-activity hours, typically late night
- morning_hours (int array): Morning hours
- work_hours (int array): Work hours
- reasoning (string): Brief explanation of configuration choices"""

        system_prompt = "You are a social media simulation expert. Return pure JSON only."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Time config LLM generation failed: {e}, using default config")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Get default time configuration (Chinese daily schedule)"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 hour per round, faster time flow
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Using default Chinese daily schedule config (1 hour per round)"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Parse time config results and validate agents_per_hour does not exceed total agent count"""
        # Get original values
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # Validate and correct: ensure not exceeding total agent count
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) exceeds total Agents ({num_entities}), corrected")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) exceeds total Agents ({num_entities}), corrected")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # Ensure min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max, corrected to {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # Default 1 hour per round
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Almost no one at dawn
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Generate event configuration"""
        
        # Get available entity type list for LLM reference
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # List representative entity names for each type
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Use configured context truncation length
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""Based on the following simulation requirements, generate an event configuration.

Simulation requirement: {simulation_requirement}

{context_truncated}

## Available entity types and examples
{type_info}

## Task
Generate an event configuration JSON:
- Extract key topic keywords
- Describe the narrative direction of public opinion
- Design initial post content — **each post must specify poster_type (the poster's entity type)**

**Important**: poster_type must be chosen from the "available entity types" above so initial posts can be assigned to the right agents.
Example: official announcements should come from Official/University types, news from MediaOutlet, student opinions from Student.

Return JSON format (no markdown):
{{
    "hot_topics": ["keyword1", "keyword2", ...],
    "narrative_direction": "<description of how public opinion will develop>",
    "initial_posts": [
        {{"content": "Post content in English", "poster_type": "EntityType (must match available types)"}},
        ...
    ],
    "reasoning": "<brief explanation>"
}}

Write all post content and descriptions in English."""

        system_prompt = "You are a public opinion analysis expert. Return pure JSON only. poster_type must exactly match an available entity type."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Event config LLM generation failed: {e}, using default config")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Using default configuration"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Parse event configuration results"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assign suitable publisher Agents for initial posts
        
        Match the most suitable agent_id for each post's poster_type
        """
        if not event_config.initial_posts:
            return event_config
        
        # Build agent index by entity type
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # Type mapping table (handle different formats LLM may output)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # Track used agent index per type, avoid reusing same agent
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Try to find matching agent
            matched_agent_id = None
            
            # 1. Direct match
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Use alias matching
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. If still not found, use highest influence agent
            if matched_agent_id is None:
                logger.warning(f"No matching Agent found for type '{poster_type}', using highest influence Agent")
                if agent_configs:
                    # Sort by influence, select highest
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"Initial post assignment: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Generate Agent configs in batches"""
        
        # Build entity info (using configured summary length)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""基于以下信息，为每个实体生成社交媒体活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合in国人作息**：凌晨0-5点几乎不活动，晚间19-22点最活跃
- **官方机构**（University/GovernmentAgency）：活跃度低(0.1-0.3)，工作时间(9-17)活动，响应慢(60-240分钟)，影响力高(2.5-3.0)
- **媒体**（MediaOutlet）：活跃度in(0.4-0.6)，全天活动(8-23)，响应快(5-30分钟)，影响力高(2.0-2.5)
- **个人**（Student/Person/Alumni）：活跃度高(0.6-0.9)，主要晚间活动(18-23)，响应快(1-15分钟)，影响力低(0.8-1.2)
- **公众人物/专家**：活跃度in(0.4-0.6)，影响力in高(1.5-2.0)

返回JSON格式（不要markdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <必须与输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时列表，考虑in国人作息>],
            "response_delay_min": <最小响应延迟分钟>,
            "response_delay_max": <最大响应延迟分钟>,
            "sentiment_bias": <-1.0到1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

        system_prompt = "你Yes社交媒体行为分析专家。返回纯JSON，配置需符合in国人作息习惯。"
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Agent config batch LLM generation failed: {e}, using rule-based generation")
            llm_configs = {}
        
        # Build AgentActivityConfig objects
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # If LLM didn't generate, use rule-based
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Generate single Agent config by rules (Chinese daily schedule)"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # Official org: work hours activity, low frequency, high influence
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: all-day activity, medium frequency, high influence
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Expert/Prof: work + evening activity, medium frequency
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Student: mainly evening, high frequency
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Morning + evening
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: mainly evening
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Lunch break + evening
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # 普通人：Evening peak
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Daytime + evening
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

