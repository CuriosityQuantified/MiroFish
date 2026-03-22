"""
Configuration Management
Unified loading of configuration from the .env file in the project root
"""

import os
from dotenv import load_dotenv

# Load the .env file from the project root
# Path: MiroFish/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root, try loading environment variables (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON configuration - disable ASCII escaping for direct display of non-ASCII characters
    JSON_AS_ASCII = False
    
    # LLM provider: 'anthropic' or 'openai'
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'anthropic')

    # LLM configuration
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.anthropic.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'claude-haiku-4-5-20251001')

    # Anthropic-specific configuration
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('LLM_API_KEY')
    ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL') or os.environ.get('LLM_BASE_URL', 'https://api.anthropic.com/v1')

    # Model names for different roles
    # Swarm agents (high volume, fast/cheap): Haiku 4.5
    LLM_SWARM_MODEL = os.environ.get('LLM_SWARM_MODEL', 'claude-haiku-4-5-20251001')
    # Orchestration and report generation: Sonnet 4.6
    LLM_ORCHESTRATION_MODEL = os.environ.get('LLM_ORCHESTRATION_MODEL', 'claude-sonnet-4-6')
    
    # Knowledge Graph configuration (Graphiti + Kuzu)
    KUZU_DB_PATH = os.environ.get('KUZU_DB_PATH', os.path.join(os.path.dirname(__file__), '../../data/kuzu_graph'))

    # Zep configuration (legacy — optional fallback)
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size
    
    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS platform available action configuration
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        if cls.LLM_PROVIDER == 'anthropic':
            if not cls.ANTHROPIC_API_KEY:
                errors.append("ANTHROPIC_API_KEY is not configured (set ANTHROPIC_API_KEY or LLM_API_KEY)")
        else:
            if not cls.LLM_API_KEY:
                errors.append("LLM_API_KEY is not configured")
        # ZEP_API_KEY is now optional (legacy fallback); Graphiti + Kuzu is default
        # if not cls.ZEP_API_KEY:
        #     errors.append("ZEP_API_KEY is not configured")
        return errors

