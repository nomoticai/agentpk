"""Pluggable language-specific signal extractors for agentpk."""

from .base import (
    EnvVarAccess,
    ExtractorBase,
    FileOperation,
    ImportRecord,
    NetworkCall,
    StaticAnalysisFindings,
    SubprocessCall,
    ToolRegistration,
)
from .go_extractor import GoExtractor
from .java_extractor import JavaExtractor
from .nodejs_extractor import NodeJSExtractor
from .python_extractor import PythonExtractor
from .registry import (
    ExtractorRegistry,
    get_extractor,
    register_extractor,
    supported_languages,
)
from .typescript_extractor import TypeScriptExtractor

# Register all built-in extractors
register_extractor(PythonExtractor())
register_extractor(NodeJSExtractor())
register_extractor(TypeScriptExtractor())
register_extractor(GoExtractor())
register_extractor(JavaExtractor())

__all__ = [
    "ExtractorBase", "StaticAnalysisFindings", "NetworkCall", "FileOperation",
    "SubprocessCall", "EnvVarAccess", "ToolRegistration", "ImportRecord",
    "ExtractorRegistry", "get_extractor", "register_extractor", "supported_languages",
    "PythonExtractor", "NodeJSExtractor", "TypeScriptExtractor", "GoExtractor", "JavaExtractor",
]
