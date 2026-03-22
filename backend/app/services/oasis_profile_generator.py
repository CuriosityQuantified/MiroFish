"""
OASIS Agent Profile Generator
Convert entities from knowledge graph to Agent Profile format required by OASIS simulation platform

Optimizations:
1. Use knowledge graph retrieval to enrich node information
2. Optimized prompts for detailed persona generation
3. Distinguish individual entities from abstract group entities
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from . import knowledge_graph as kg

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Optional fields - Reddit style
    karma: int = 1000
    
    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Additional persona info
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Source entity info
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Add additional persona info (if available)
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Add additional persona info
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dictionary format"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator
    
    Convert Zep graph entities to Agent Profiles for OASIS simulation
    
    Optimization features:
    1. Use Zep graph retrieval for richer context
    2. Generate very detailed personas (including basic info, career, personality, social media behavior, etc.)
    3. Distinguish individual entities from abstract group entities
    """
    
    # MBTI type list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Common countries list
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individual entity types (need specific persona)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Group/organization entity types (need representative persona)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None,
        provider: Optional[str] = None
    ):
        self.provider = provider or Config.LLM_PROVIDER
        # Use orchestration model for profile generation (more capable)
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
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        
        # Knowledge graph client for retrieving rich context
        self.graph_id = graph_id
        # Graphiti + Kuzu is always available (embedded, no API key needed)
        self._kg_available = True
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Generate OASIS Agent Profile from Zep entity
        
        Args:
            entity: Zep entity node
            user_id: User ID (for OASIS)
            use_llm: Whether to use LLM for detailed persona
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Basic info
        name = entity.name
        user_name = self._generate_username(name)
        
        # Build context info
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Use LLM for detailed persona
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Use rules for basic persona
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Generate username"""
        # Remove special chars, convert to lowercase
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Add random suffix to avoid duplicates
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Use Zep graph hybrid search to get rich entity information
        
        Zep has no built-in hybrid search API, need to search edges and nodes separately then merge results.
        Use parallel requests for both searches to improve efficiency.
        
        Args:
            entity: Entity node object
            
        Returns:
            Dictionary with facts, node_summaries, context
        """
        import concurrent.futures
        
        if not self._kg_available:
            return {"facts": [], "node_summaries": [], "context": ""}

        entity_name = entity.name

        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }

        # Must have graph_id to perform search
        if not self.graph_id:
            logger.debug(f"Skipping graph retrieval: graph_id not set")
            return results

        comprehensive_query = f"All information, activities, events, relationships and background about {entity_name}"

        try:
            # Use Graphiti hybrid search via knowledge_graph module
            search_edges = kg.search_graph(
                graph_id=self.graph_id,
                query=comprehensive_query,
                limit=30,
            )

            # Process edge search results
            all_facts = set()
            for edge in search_edges:
                fact = edge.get('fact', '')
                if fact:
                    all_facts.add(fact)
            results["facts"] = list(all_facts)

            # Get nodes for entity summaries
            all_nodes = kg.get_all_nodes(self.graph_id)
            all_summaries = set()
            for node in all_nodes:
                if node.get('summary'):
                    all_summaries.add(node['summary'])
                if node.get('name') and node['name'] != entity_name:
                    all_summaries.add(f"Related entity: {node['name']}")
            results["node_summaries"] = list(all_summaries)

            # Build comprehensive context
            context_parts = []
            if results["facts"]:
                context_parts.append("Factual information:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)

            logger.info(f"Graph hybrid search complete: {entity_name}, got {len(results['facts'])} facts, {len(results['node_summaries'])} related nodes")

        except Exception as e:
            logger.warning(f"Graph retrieval failed ({entity_name}): {e}")

        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Build complete context information for entity
        
        Includes:
        1. Entity edge info (facts)
        2. Related node details
        3. Rich info from knowledge graph hybrid search
        """
        context_parts = []
        
        # 1. Add entity attribute info
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity Attributes\n" + "\n".join(attrs))
        
        # 2. Add related edge info (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # 不限制数量
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (related entity)")
                    else:
                        relationships.append(f"- (related entity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Related Facts and Relationships\n" + "\n".join(relationships))
        
        # 3. Add related node details
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # 不限制数量
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # 过滤掉默认标签
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Related Entity Information\n" + "\n".join(related_info))
        
        # 4. Use knowledge graph hybrid search for richer info
        kg_results = self._search_zep_for_entity(entity)

        if kg_results.get("facts"):
            # Deduplicate: exclude existing facts
            new_facts = [f for f in kg_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Facts Retrieved from Knowledge Graph\n" + "\n".join(f"- {f}" for f in new_facts[:15]))

        if kg_results.get("node_summaries"):
            context_parts.append("### Related Nodes from Knowledge Graph\n" + "\n".join(f"- {s}" for s in kg_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Check if entity is individual type"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Check if entity is group/organization type"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Use LLM to generate very detailed persona
        
        Distinguish by entity type:
        - Individual entity: generate specific character settings
        - Group/organization entity: generate representative account settings
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Try multiple times until success or max retries
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                temperature = 0.7 - (attempt * 0.1)  # 每次retry降低温度
                system_prompt = self._get_system_prompt(is_individual)

                if self._use_anthropic_sdk:
                    json_instruction = "\n\nIMPORTANT: You must respond with valid JSON only, no markdown formatting."
                    response = self.client.messages.create(
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
                    if finish_reason == 'max_tokens':
                        logger.warning(f"LLM output truncated (attempt {attempt+1}), attempting fix...")
                        content = self._fix_truncated_json(content)
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
                    if finish_reason == 'length':
                        logger.warning(f"LLM output truncated (attempt {attempt+1}), attempting fix...")
                        content = self._fix_truncated_json(content)
                
                # Try to parse JSON
                try:
                    result = json.loads(content)
                    
                    # Validate required fields
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # Try to fix JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # 指数退避
        
        logger.warning(f"LLM persona generation failed ({max_attempts} attempts): {last_error}, using rule-based generation")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON (output truncated by max_tokens limit)"""
        import re
        
        # If JSON is truncated, try to close it
        content = content.strip()
        
        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed strings
        # Simple check: if no comma or closing bracket after last quote, string may be truncated
        if content and content[-1] not in '",}]':
            # Try to close string
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Try to fix corrupted JSON"""
        import re
        
        # 1. First try to fix truncation
        content = self._fix_truncated_json(content)
        
        # 2. Try to extract JSON part
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Handle newline issues in strings
            # Find all string values and replace newlines
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace actual newlines in strings with spaces
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Replace excess spaces
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Match JSON string values
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Try to parse
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. If still failing, try more aggressive fix
                try:
                    # Remove all control characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Replace all consecutive whitespace
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Try to extract partial info from content
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # 可能被截断
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a {entity_type}.")
        
        # If meaningful content extracted, mark as fixed
        if bio_match or persona_match:
            logger.info(f"Extracted partial info from corrupted JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Complete failure, return basic structure
        logger.warning(f"JSON fix failed, returning basic structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a {entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Get system prompt"""
        base_prompt = "You are a social media user profile generation expert. Generate detailed, realistic personas for public opinion simulation, maximizing fidelity to known real-world situations. Must return valid JSON format, all string values must not contain unescaped newlines. Use Chinese."
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for individual entity"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "No additional context"
        
        return f"""Generate detailed social media user persona for entity, maximizing fidelity to known real-world situations.

Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context information:
{context_str}

Please generate JSON with the following fields:

1. bio: Social media bio, 200 characters
2. persona: 详细人设描述（2000字's纯文本），需包含:
   - Basic info (age, occupation, education, location)
   - 人物背景（重要经历、与事件's关联、社会关系）
   - Personality traits (MBTI type, core personality, emotional expression)
   - Social media behavior (posting frequency, content preference, interaction style, language traits)
   - 立场观点（对话题's态度、可能被激怒/感动's内容）
   - Unique traits (catchphrases, special experiences, hobbies)
   - 个人记忆（人设's重要部分，要介绍这个个体与事件's关联，以及这个个体在事件in's已有动作与反应）
3. age: 年龄数字（必须Yes整数）
4. gender: 性别，必须Yes英文: "male" or "female"
5. mbti: MBTI type (e.g., INTJ, ENFP)
6. country: 国家（使用in文，如"in国"）
7. profession: Profession
8. interested_topics: Array of interested topics

Important:
- 所有字段值必须Yes字符串or数字，不要使用换行符
- persona必须Yes一段连贯's文字描述
- 使用in文（除了gender字段必须用英文male/female）
- Content must be consistent with entity information
- age必须Yes有效's整数，gender必须Yes"male"or"female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for group/organization entity"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "No additional context"
        
        return f"""Generate detailed social media account settings for organization/group entity, maximizing fidelity to known real-world situations.

Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context information:
{context_str}

Please generate JSON with the following fields:

1. bio: Official account bio, 200 chars, professional
2. persona: 详细账号设定描述（2000字's纯文本），需包含:
   - Organization basics (formal name, nature, founding, main functions)
   - Account positioning (type, target audience, core functions)
   - Speaking style (language traits, common expressions, taboo topics)
   - Content characteristics (content type, posting frequency, active hours)
   - 立场态度（对核心话题's官方立场、面对争议's处理方式）
   - 特殊说明（代表's群体画像、运营习惯）
   - 机构记忆（机构人设's重要部分，要介绍这个机构与事件's关联，以及这个机构在事件in's已有动作与反应）
3. age: 固定填30（机构账号's虚拟年龄）
4. gender: Fixed as "other" (institutional accounts use other for non-personal)
5. mbti: MBTI type to describe account style, e.g., ISTJ for rigorous/conservative
6. country: 国家（使用in文，如"in国"）
7. profession: Institutional function description
8. interested_topics: Array of focus areas

Important:
- 所有字段值必须Yes字符串or数字，不允许null值
- persona必须Yes一段连贯's文字描述，不要使用换行符
- 使用in文（除了gender字段必须用英文"other"）
- age必须Yes整数30，gender必须Yes字符串"other"
- Institutional account speech must match its identity positioning"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate basic persona using rules"""
        
        # Generate different personas based on entity type
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Organization virtual age
                "gender": "other",  # Organization uses other
                "mbti": "ISTJ",  # Organization style: rigorous and conservative
                "country": "in国",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Organization virtual age
                "gender": "other",  # Organization uses other
                "mbti": "ISTJ",  # Organization style: rigorous and conservative
                "country": "in国",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Default persona
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Set graph ID for knowledge graph retrieval"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Batch generate Agent Profiles from entities (supports parallel generation)
        
        Args:
            entities: Entity list
            use_llm: Whether to use LLM for detailed persona
            progress_callback: Progress callback function (current, total, message)
            graph_id: Graph ID for knowledge graph retrieval to get richer context
            parallel_count: Parallel generation count, default 5
            realtime_output_path: Real-time write file path (if provided, write after each generation)
            output_platform: Output platform format ("reddit" or "twitter")
            
        Returns:
            Agent Profile list
        """
        import concurrent.futures
        from threading import Lock
        
        # Set graph_id for knowledge graph retrieval
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # 预分配列表保持顺序
        completed_count = [0]  # Use列表以便在闭包in修改
        lock = Lock()
        
        # Helper function for real-time file writing
        def save_profiles_realtime():
            """Save generated profiles to file in real-time"""
            if not realtime_output_path:
                return
            
            with lock:
                # Filter out generated profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Real-time profile save failed: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function for generating a single profile"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Output generated persona to console and log in real-time
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Failed to generate persona for entity {entity.name}: {str(e)}")
                # Create a basic profile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Starting parallel generation of {total} Agent personas (parallelism: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"Starting Agent persona generation - {total} entities, parallelism: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Execute in parallel using thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Submit all tasks
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Write to file in real-time
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completed {current}/{total}: {entity.name} ({entity_type})"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} using fallback persona: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Successfully generated persona: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"Exception processing entity {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Write to file in real-time（即使Yes备用人设）
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"Persona generation complete! Generated {len([p for p in profiles if p])} Agents")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Output generated persona to console in real-time (full content, no truncation)"""
        separator = "-" * 70
        
        # Build full output content (no truncation)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'
        
        output_lines = [
            f"\n{separator}",
            f"[Generated] {entity_name} ({entity_type})",
            f"{separator}",
            f"Username: {profile.user_name}",
            f"",
            f"[Bio]",
            f"{profile.bio}",
            f"",
            f"[Detailed Persona]",
            f"{profile.persona}",
            f"",
            f"[Basic Attributes]",
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}",
            f"Profession: {profile.profession} | Country: {profile.country}",
            f"Interests: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Output to console only (avoid duplication, logger no longer outputs full content)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Save Profiles to file (select correct format by platform)
        
        OASIS platform format requirements:
        - Twitter: CSV格式
        - Reddit: JSON格式
        
        Args:
            profiles: Profile list
            file_path: 文件路径
            platform: Platform type ("reddit" or "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Twitter Profile as CSV (compliant with OASIS requirements)
        
        OASIS Twitter required CSV fields:
        - user_id: User ID (starting from 0 based on CSV order)
        - name: User's real name
        - username: System username
        - user_char: Detailed persona description (injected into LLM system prompt to guide Agent behavior)
        - description: Short public bio (displayed on user profile page)
        
        user_char vs description difference:
        - user_char: Internal use, LLM system prompt, determines how Agent thinks and acts
        - description: External display, bio visible to other users
        """
        import csv
        
        # Ensure file extension is .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write OASIS required headers
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Write data rows
            for idx, profile in enumerate(profiles):
                # user_char: Full persona (bio + persona), for LLM system prompt
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Handle newlines (replace with spaces in CSV)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: Short bio, for external display
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: Sequential ID starting from 0
                    profile.name,           # name: Real name
                    profile.user_name,      # username: Username
                    user_char,              # user_char: Full persona (internal LLM use)
                    description             # description: Short bio (external display)
                ]
                writer.writerow(row)
        
        logger.info(f"Saved {len(profiles)} Twitter Profiles to {file_path} (OASIS CSV format)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Normalize gender field to OASIS required English format
        
        OASIS requires: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # Chinese mapping
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # 英文已有
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Reddit Profile as JSON format
        
        Use format consistent with to_reddit_format(), ensure OASIS can read correctly.
        Must include user_id field, this is key for OASIS agent_graph.get_agent() matching!
        
        Required fields:
        - user_id: 用户ID（整数，用于匹配 initial_posts in's poster_agent_id）
        - username: 用户名
        - name: 显示名称
        - bio: 简介
        - persona: 详细人设
        - age: 年龄（整数）
        - gender: "male", "female", or "other"
        - mbti: MBTI类型
        - country: 国家
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Use format consistent with to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Critical: must include user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS required fields - ensure all have defaults
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "in国",
            }
            
            # Optional fields
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(profiles)} Reddit Profiles to {file_path} (JSON format, with user_id field)")
    
    # Keep old method name as alias for backward compatibility
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecated] Please use save_profiles() method"""
        logger.warning("save_profiles_to_json is deprecated, please use save_profiles method")
        self.save_profiles(profiles, file_path, platform)

