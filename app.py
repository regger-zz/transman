# app.py - Core of the SAS QA Translation Framework
import streamlit as st
import sas_lexer  # Your new, custom-installed tokenizer
import pandas as pd  # For eventual validation reports
import hashlib  # For secure password hashing
# import json  # To handle blueprint serialization
 
# ====================
# PASSWORD GATE
# ====================
# This section runs FIRST on every page load
def check_password():
    """Returns `True` if the user had the correct password."""

    # Check if the password is already verified in the session state
    if st.session_state.get("password_verified"):
        return True

    # If not, show the password input form
    st.title("🔒 SAS Translation Tool - Private Preview")
    st.markdown("This is a private prototype. Please enter the access key.")
    
    # Use a text input with type='password' to hide characters
    password_input = st.text_input("Access Key:", type="password", key="password_input")
    
    # Create columns to center the unlock button
    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        unlock_button = st.button("🔓 Unlock Tool", type="primary", use_container_width=True)

    # Check the password when the button is pressed
    if unlock_button:
        # 1. Hash the input for secure comparison (don't store or compare plain text)
        input_hash = hashlib.sha256(password_input.encode()).hexdigest()
        
        # 2. Compare against the *hash* of your secret password
        # IMPORTANT: Replace 'YourActualPassword123!' with your chosen strong password
        # Then compute its SHA256 hash and paste the hash value below.
        # You can get the hash by running this in a Python terminal:
        # import hashlib; print(hashlib.sha256("YourActualPassword123!".encode()).hexdigest())
        CORRECT_HASH = "3eef6ef9df84af5f980aef579e45993b2507652fc0a7384b4cbea7b4f1c7cc2b"  # <-- REPLACE THIS ENTIRE STRING
        
        if input_hash == CORRECT_HASH:
            st.session_state.password_verified = True
            st.rerun()  # Rerun the script to now show the main app
        else:
            st.error("Incorrect access key. Please try again.")
    
    # If we reach here, the password is not verified yet
    st.stop()  # Stop execution; nothing below this runs

# Call the function. If password is wrong, `st.stop()` halts the app.
check_password()


# ====================
# PAGE CONFIGURATION
# ====================
st.set_page_config(
    page_title="SAS-to-SQL/Python QA Framework",
    page_icon="🔬",
    layout="wide"
)

# ====================
# APP TITLE & INTRO
# ====================
st.title("🔬 SAS-to-SQL/Python QA Translation Framework")
st.markdown("""
This tool implements a **two-stage, quality-assured process** for migrating SAS code.
1.  **Stage 1: Analysis & Blueprint** – Automatically scans your SAS code for complexity and risks.
2.  **Stage 2: Governed Translation & Validation** – Safely translates and verifies the output.
""")

# ====================
# BLUEPRINT GENERATION FUNCTION
# ====================
def generate_blueprint(tokens, raw_sas_code):
    """
    Analyze SAS tokens to create a translation blueprint.
    Production version - clean, focused, reliable.
    """
    # Initialize counters and trackers
    analysis = {
        "data_steps": 0,
        "proc_blocks": 0,
        "proc_sql_blocks": 0,
        "macro_definitions": 0,
        "macro_calls": 0,
        "proc_types": set(),
        "datasets_created": set(),
        "datasets_used": set(),
        "has_retain": False,
        "has_lag": False,
        "has_merge": False,
        "has_arrays": False,
        "in_data_step": False,
        "in_proc_block": False,
        "current_proc": None,
        "pointer_controls": 0,      # Count of @n pointers
        "line_hold_single": False,  # Single @ at end of INPUT
        "line_hold_double": False,  # Double @@ at end of INPUT
        "platform_concerns": [],    # List of platform-specific issues found
        "has_proc_import": False,
    }
    
    # Helper: Safe token text extraction
    def get_token_text_safe(token_idx):
        if token_idx >= len(tokens) or token_idx < 0:
            return None
        token = tokens[token_idx]
        return raw_sas_code[token.start:token.stop].upper()
    
    # Helper: Safe token type check
    def get_token_type_safe(token_idx):
        if token_idx >= len(tokens) or token_idx < 0:
            return None
        return tokens[token_idx].token_type.name
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        token_text = raw_sas_code[token.start:token.stop].upper()
        token_type = token.token_type.name
        
        # Skip whitespace and comments
        if token_type in ['WS', 'COMMENT']:
            i += 1
            continue
        
        # --- DETECT PROC SORT PARAMETERS ---
        if analysis["current_proc"] == 'SORT' and token_text in ['DATA', 'OUT']:
            # Find '=' after DATA/OUT
            eq_pos = i + 1
            while eq_pos < len(tokens) and get_token_type_safe(eq_pos) == 'WS':
                eq_pos += 1
            
            if eq_pos < len(tokens) and get_token_text_safe(eq_pos) == '=':
                # Find dataset name after '='
                ds_pos = eq_pos + 1
                while ds_pos < len(tokens) and get_token_type_safe(ds_pos) == 'WS':
                    ds_pos += 1
                
                if ds_pos < len(tokens) and get_token_type_safe(ds_pos) in ['IDENT', 'IDENTIFIER']:
                    ds_name = raw_sas_code[tokens[ds_pos].start:tokens[ds_pos].stop]
                    if token_text == 'DATA':
                        analysis["datasets_used"].add(ds_name)
                    elif token_text == 'OUT':
                        analysis["datasets_created"].add(ds_name)
        
        # --- DETECT DATA STEPS ---
        elif token_text == 'DATA' and not analysis["in_data_step"]:
            # Check it's not part of a function or PROC parameter
            next_text = get_token_text_safe(i+1)
            if next_text and next_text not in ['_NULL_', 'STEP', '='] and not next_text.startswith('('):
                analysis["data_steps"] += 1
                analysis["in_data_step"] = True
                
                # Capture dataset name (handle variable whitespace)
                name_pos = i + 1
                while name_pos < len(tokens) and get_token_type_safe(name_pos) == 'WS':
                    name_pos += 1
                
                if name_pos < len(tokens) and get_token_type_safe(name_pos) in ['IDENT', 'IDENTIFIER']:
                    ds_name = raw_sas_code[tokens[name_pos].start:tokens[name_pos].stop]
                    analysis["datasets_created"].add(ds_name)
        
        # --- DETECT PROC BLOCKS ---
        elif token_text == 'PROC':
            # Find procedure name, skipping whitespace
            proc_pos = i + 1
            while proc_pos < len(tokens) and get_token_type_safe(proc_pos) == 'WS':
                proc_pos += 1
            
            if proc_pos < len(tokens):
                proc_name = get_token_text_safe(proc_pos)
                if proc_name and proc_name.isalpha():
                    proc_name = proc_name.upper()
                    analysis["proc_types"].add(proc_name)
                    analysis["proc_blocks"] += 1
                    analysis["in_proc_block"] = True
                    analysis["current_proc"] = proc_name

                    # Special flag for high-complexity procedures
                    if proc_name == 'IMPORT':
                        analysis["has_proc_import"] = True

                    if proc_name == 'SQL':
                        analysis["proc_sql_blocks"] += 1
        
        # --- DETECT SET/MERGE REFERENCES ---
        elif token_text in ['SET', 'MERGE', 'UPDATE', 'MODIFY'] and analysis["in_data_step"]:
            # Find dataset name after the keyword
            ds_pos = i + 1
            while ds_pos < len(tokens) and get_token_type_safe(ds_pos) == 'WS':
                ds_pos += 1
            
            if ds_pos < len(tokens) and get_token_type_safe(ds_pos) in ['IDENT', 'IDENTIFIER']:
                ds_name = raw_sas_code[tokens[ds_pos].start:tokens[ds_pos].stop]
                analysis["datasets_used"].add(ds_name)
        
        # --- DETECT MACROS ---
        elif token_text.startswith('%'):
            if token_text == '%MACRO':
                analysis["macro_definitions"] += 1
            else:
                analysis["macro_calls"] += 1
        
        # --- DETECT COMPLEXITY PATTERNS ---
        elif token_text == 'RETAIN':
            analysis["has_retain"] = True
        elif token_text in ['LAG', 'LAG1', 'LAG2']:
            analysis["has_lag"] = True
        elif token_text == 'MERGE':
            analysis["has_merge"] = True
        elif token_text == 'ARRAY':
            analysis["has_arrays"] = True

        # --- DETECT @ PATTERNS ---
        elif token_text == '@':
            # Check what type of @ this is
            # Look ahead to see if it's @@ or @n
            if i+1 < len(tokens):
                next_text = get_token_text_safe(i+1)
                
                # Case 1: @@ (double line hold)
                if next_text == '@':
                    analysis["line_hold_double"] = True
                    i += 1  # Skip the second @
                
                # Case 2: @n (pointer control with number)
                elif next_text and next_text.isdigit():
                    analysis["pointer_controls"] += 1
                    i += 1  # Skip the number
                
                # Case 3: Single @ (could be line hold, need more context)
                else:
                    # We'll determine if it's line hold later based on position
                    pass
        
        # --- DETECT PLATFORM CONCERNS ---
        # X command (immediate host execution)
        elif token_text == 'X':
            analysis["platform_concerns"].append("X command (host-specific execution)")
        
        # FILENAME/LIBNAME (often OS-specific paths)
        elif token_text in ['FILENAME', 'LIBNAME']:
            analysis["platform_concerns"].append(f"{token_text} statement (check path portability)")
        
        # CALL SYSTEM (function-based execution)
        elif token_text == 'CALL' and i+1 < len(tokens):
            next_text = get_token_text_safe(i+1)
            if next_text == 'SYSTEM':
                analysis["platform_concerns"].append("CALL SYSTEM() (host command execution)")
        
        # --- DETECT BLOCK ENDINGS ---
        elif token_text in ['RUN', 'QUIT', 'DATALINES']:
            analysis["in_data_step"] = False
            analysis["in_proc_block"] = False
            analysis["current_proc"] = None
        
        i += 1
    
    # --- CALCULATE COMPLEXITY SCORE ---
    complexity_score = (
        analysis["data_steps"] * 1 +
        analysis["proc_blocks"] * 1 +
        analysis["proc_sql_blocks"] * 2 +
        analysis["macro_definitions"] * 5 +
        analysis["macro_calls"] * 2 +
        (5 if analysis["has_retain"] else 0) +
        (5 if analysis["has_lag"] else 0) +
        (3 if analysis["has_merge"] else 0) +
        (3 if analysis["has_arrays"] else 0) +
        (analysis["pointer_controls"] * 2) +       # @n pointers add some complexity
        (10 if analysis["line_hold_double"] else 0) + # @@ is high complexity
        (8 if analysis["line_hold_single"] else 0) +  # @ is high complexity
        (len(analysis["platform_concerns"]) * 3)   # Each platform concern adds risk
        + (10 if analysis["has_proc_import"] else 0)
    )
    
    # Determine priority
    if complexity_score > 25:
        priority = "High"
        confidence = "Manual review strongly recommended"
    elif complexity_score > 15:
        priority = "Medium"
        confidence = "Mixed automation with oversight"
    else:
        priority = "Low"
        confidence = "Good candidate for automated translation"
    
    # Generate recommendations
    recommendations = []
    if analysis["macro_definitions"] > 0:
        recommendations.append("**Manual review required for custom macro definitions.**")
    if analysis["proc_sql_blocks"] > 0:
        recommendations.append(f"**Verify logic of {analysis['proc_sql_blocks']} PROC SQL block(s).**")
    if analysis["has_retain"]:
        recommendations.append("**RETAIN statements require stateful translation logic.**")
    if analysis["has_lag"]:
        recommendations.append("**LAG functions need special handling for row context.**")
    if not recommendations:
        recommendations.append("**Code structure appears straightforward for automated translation.**")
    if analysis["pointer_controls"] > 0:
        recommendations.append(f"**Column pointer controls (@) detected: {analysis['pointer_controls']} instance(s). Requires careful input parsing translation.**")
    
    if analysis["line_hold_single"]:
        recommendations.append("**Single trailing @ detected: Line hold requires stateful INPUT buffer management.**")
    
    if analysis["line_hold_double"]:
        recommendations.append("**Double trailing @@ detected: Complex line hold across multiple records.**")
    
    # NEW: Platform concerns
    if analysis["platform_concerns"]:
        unique_concerns = list(set(analysis["platform_concerns"]))
        concerns_text = ", ".join(sorted(unique_concerns))
        recommendations.append(f"**Platform-specific code: {concerns_text}. Review for portability.**")

    if analysis["has_proc_import"]:
        recommendations.append("**PROC IMPORT detected: Requires manual mapping to pandas.read_csv()/read_excel() with specific parameter analysis.**")

    # --- STRUCTURE FINAL BLUEPRINT ---
    blueprint = {
        "summary": {
            "translation_priority": priority,
            "confidence_assessment": confidence,
            "complexity_score": complexity_score,
            "total_lines": len(raw_sas_code.split('\n')),
            "total_tokens": len(tokens)
        },
        "detailed_counts": {
            "DATA Steps": analysis["data_steps"],
            "PROC Blocks": analysis["proc_blocks"],
            "PROC SQL Blocks": analysis["proc_sql_blocks"],
            "Macro Definitions": analysis["macro_definitions"],
            "Macro Calls": analysis["macro_calls"],
            "PROC Types Found": list(sorted(analysis["proc_types"]))
        },
        "data_flow": {
            "datasets_created": list(sorted(analysis["datasets_created"])),
            "datasets_used": list(sorted(analysis["datasets_used"]))
        },
        "complexity_flags": {
            "has_retain_statement": analysis["has_retain"],
            "has_lag_function": analysis["has_lag"],
            "has_merge_statement": analysis["has_merge"],
            "has_array_declarations": analysis["has_arrays"],
            "pointer_controls_count": analysis["pointer_controls"],
            "has_line_hold_single": analysis["line_hold_single"],
            "has_line_hold_double": analysis["line_hold_double"],
            "platform_concerns": analysis["platform_concerns"]
        },  
        "recommendations": recommendations
    }
    st.write("Quick structure check:", list(blueprint.keys()))
    st.write("Detailed counts:", blueprint.get("detailed_counts", "MISSING"))

    return blueprint

def display_blueprint(blueprint, tokens, raw_sas_code):
    """Display the blueprint in a clean, single container"""

    st.sidebar.write("🔍 DEBUG: display_blueprint called")
    st.sidebar.write(f"Blueprint keys: {list(blueprint.keys())}")
    st.sidebar.write(f"Has 'detailed_counts': {'detailed_counts' in blueprint}")
    blueprint_container = st.container()
    
    with blueprint_container:
        st.subheader("📋 Analysis Blueprint")
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Priority", blueprint["summary"]["translation_priority"])
        with col2:
            st.metric("Complexity Score", blueprint["summary"]["complexity_score"])
        with col3:
            st.metric("DATA Steps", blueprint["detailed_counts"]["DATA Steps"])
        
        # SINGLE instance of each section
        with st.expander("📊 Detailed Counts", expanded=False):
            st.json(blueprint["detailed_counts"])
        
        with st.expander("📁 Data Flow", expanded=False):
            created = blueprint["data_flow"]["datasets_created"]
            used = blueprint["data_flow"]["datasets_used"]
            st.write("**Created:**", ", ".join(created) if created else "None")
            st.write("**Used:**", ", ".join(used) if used else "None")
        
        with st.expander("🚩 Complexity Flags", expanded=False):
            st.json(blueprint["complexity_flags"])
        
        with st.expander("⚠️ Recommendations", expanded=False):
            for rec in blueprint["recommendations"]:
                st.markdown(f"- {rec}")
        
        # OPTIONAL: Keep token preview for debugging
        with st.expander("🔎 Preview first 150 tokens (Debug)", expanded=False):
            preview_data = []
            for idx, token_obj in enumerate(tokens[:150]):
                token_text = raw_sas_code[token_obj.start:token_obj.stop]
                token_kind = token_obj.token_type.name
                preview_data.append({
                    "Index": idx,
                    "Text": token_text,
                    "Kind": token_kind
                })
            st.table(preview_data)
    
    return blueprint_container

# ====================
# STAGE 1: UPLOAD & INITIAL PROCESSING
# ====================
st.header("📁 Stage 1: Upload & Analyze")

if st.button("🔄 Start New Analysis"):
    for key in ['blueprint_generated', 'current_blueprint', 'raw_sas_code', 'last_file_id', 'should_display_blueprint', 'current_tokens',
                'already_displayed']:
        if key in st.session_state:   
            del st.session_state[key]
    st.rerun()

uploaded_file = st.file_uploader("Upload your SAS script (.sas)", type=['sas'])
raw_sas_code = ""
current_file_id = None 

if uploaded_file is not None:
    current_file_id = f"{uploaded_file.name}_{uploaded_file.size}" 
    raw_sas_code = uploaded_file.read().decode()
    
    # Display the uploaded code for immediate review
    with st.expander("📄 View Uploaded SAS Code", expanded=False):
        st.code(raw_sas_code, language='sas')
    
    # ====================
    # CORE LEXING STEP
    # ====================
    if st.button("🔍 Generate Analysis Blueprint", type="primary"):
        if ('last_file_id' in st.session_state and 
            st.session_state.last_file_id == current_file_id and
            'blueprint_generated' in st.session_state and 
            st.session_state.blueprint_generated):
                st.info("Blueprint already generated for this file. Upload a new file to analyze again.")
        else:        
            # Inform the user that processing has started
            with st.spinner("Lexing and analyzing SAS code..."):
            
                # -------------------------------------
                # THIS IS WHERE sas-lexer DOES ITS WORK
                # -------------------------------------
                try:
                    # Pass the raw code string to the lexer
                    lex_result = sas_lexer.lex_program_from_str(raw_sas_code)
                    
                    # Unpack the 3-item tuple correctly
                    tokens, errors, _ = lex_result  # We ignore the 3rd bytes item
                    
                    # Check for lexing errors
                    if errors:
                        st.warning(f"⚠️ Lexing completed with {len(errors)} warnings")
                        
                    # Basic confirmation for the user
                    st.success(f"✅ Lexing complete. Found {len(tokens)} tokens.")
                   
                    # --- Generate and Display the Blueprint ---
                    blueprint = generate_blueprint(tokens, raw_sas_code)
                    
                    # Store for Stage 2 AND for display (DON'T display here)
                    st.session_state.current_blueprint = blueprint
                    st.session_state.current_tokens = tokens  # Store tokens too
                    st.session_state.raw_sas_code = raw_sas_code
                    st.session_state.blueprint_generated = True
                    st.session_state.last_file_id = current_file_id
                    st.session_state.should_display_blueprint = True  # New flag

                    # Temporary debug
                    st.sidebar.write("Debug - Session State:")
                    st.sidebar.write(f"should_display_blueprint: {'should_display_blueprint' in st.session_state}")
                    if 'should_display_blueprint' in st.session_state:
                        st.sidebar.write(f"Value: {st.session_state.should_display_blueprint}")
                    st.sidebar.write(f"current_blueprint exists: {'current_blueprint' in st.session_state}")
                    
                    # --- CONDITIONAL BLUEPRINT DISPLAY ---
                    # This runs AFTER the button logic, on every script re-run

                    if ('should_display_blueprint' in st.session_state and 
                        st.session_state.should_display_blueprint and
                        'current_blueprint' in st.session_state and
                        'current_tokens' in st.session_state):

                        if not st.session_state.get('already_displayed', False):  
                            st.write("TEST: About to display blueprint")
                            st.write(f"Recommendations count: {len(blueprint['recommendations'])}")

                            # Display the blueprint using session state data
                            display_blueprint(
                                st.session_state.current_blueprint,
                                st.session_state.current_tokens,
                                st.session_state.raw_sas_code
                            )

                except Exception as e:
                    st.error(f"❌ Lexing failed: {e}")
                    st.info("This might be due to extremely complex or malformed SAS syntax.")
                    
