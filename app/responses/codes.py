from enum import Enum

class ResponseCode(str, Enum):
    # Search / Specification
    PRODUCT_NOT_FOUND = "product_not_found"
    MISSING_PRODUCT_NAME = "missing_product_name"
    SEARCH_HEADER = "search_header"
    SPECIFICATION_FALLBACK = "specification_fallback"
    SPECIFICATION_DETAIL_UNAVAILABLE = "specification_detail_unavailable"
    
    # Suggestion
    MISSING_ORIGIN_COMPONENT = "missing_origin_component"
    NO_COMPATIBLE_SUGGESTIONS = "no_compatible_suggestions"
    SUGGESTION_HEADER = "suggestion_header"
    SUGGESTION_NOT_SUPPORTED = "suggestion_not_supported"
    
    # Price
    MISSING_PRICE_TERMS = "missing_price_terms"
    PRICE_CHECK_FALLBACK = "price_check_fallback"
    PRICE_CALCULATION_FALLBACK = "price_calculation_fallback"
    
    # Compatibility
    COMPATIBILITY_MISSING_INFO = "compatibility_missing_info"
    COMPATIBILITY_FALLBACK = "compatibility_fallback"

    # PC Builder Clarification
    MISSING_BUDGET = "missing_budget"
    MISSING_PURPOSE = "missing_purpose"

    # PC Builder Errors
    BUDGET_SCOPE_AMBIGUOUS = "budget_scope_ambiguous"
    COMPONENT_NOT_FOUND = "component_not_found"
    COMPONENTS_INCOMPATIBLE = "components_incompatible"
    MERGE_ERROR = "merge_error"
    MISSING_SELECTED_BUILD = "missing_selected_build"
    BUILD_NOT_FOUND = "build_not_found"
    NO_CANDIDATE_BUILD = "no_candidate_build"

    # Input Guard / Chat
    INPUT_TOO_LONG = "input_too_long"
    EMPTY_INPUT = "empty_input"
    INVALID_FORMAT = "invalid_format"
    UNSAFE_CONTENT = "unsafe_content"
    OUT_OF_SCOPE = "out_of_scope"
    GREETING = "greeting"
    UNRECOGNIZED_INTENT = "unrecognized_intent"
    
    # Infrastructure Failures
    ROUTING_UNAVAILABLE = "routing_unavailable"
    LLM_UNAVAILABLE = "llm_unavailable"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    SYSTEM_ERROR = "system_error"


class ResponseGenerationUnavailable(RuntimeError):
    pass


class CatalogUnavailable(RuntimeError):
    pass
