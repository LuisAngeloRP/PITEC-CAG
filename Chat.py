import streamlit as st
import db_manager as db
from datetime import datetime
from agents.conversational_agent import ConversationalAgent
from agents.cag_agent import CAGAgent
import document_db_manager as doc_db
import json
import os
import re
import base64

def init_chat_state():
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = db.create_conversation()
    if "current_document_db" not in st.session_state:
        # Obtener la primera base de datos disponible
        databases = doc_db.get_document_databases()
        st.session_state.current_document_db = databases[0]['name'] if databases else None
    if "agents" not in st.session_state:
        conv_agent = ConversationalAgent()
        cag_agent = CAGAgent()
        conv_agent.set_cag_agent(cag_agent)
        st.session_state.agents = {
            "conversational": conv_agent,
            "cag": cag_agent
        }
        # Configurar la base de datos inicial para el agente CAG
        if st.session_state.current_document_db:
            st.session_state.agents["cag"].set_database(st.session_state.current_document_db)
    
    # Asegurarse de que el agente tenga el ID de conversación correcto
    st.session_state.agents["conversational"].set_conversation_id(
        st.session_state.current_conversation_id
    )

def format_time(timestamp):
    dt = datetime.strptime(timestamp[:16], '%Y-%m-%d %H:%M')
    return dt.strftime('%d %b, %H:%M')

def create_download_link(db_name, filename):
    """Crea un enlace de descarga para un documento"""
    # Construir la ruta completa al archivo
    file_path = os.path.join('documents', db_name, filename)
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            file_content = f.read()
        return file_content
    return None

def format_reference_with_download(reference, db_name):
    """Formatea una referencia con un enlace de descarga si el archivo existe"""
    # Extraer el nombre del archivo de la referencia
    filename = reference.split(" - ")[0] if " - " in reference else reference
    filename = filename.strip()  # Eliminar espacios en blanco
    
    # Eliminar el [X] del nombre del archivo si existe
    filename = re.sub(r'\[\d+\]\s*', '', filename).strip()
    
    file_content = create_download_link(db_name, filename)
    if file_content:
        # Convertir el contenido del archivo a base64 para usarlo en el href
        b64_content = base64.b64encode(file_content).decode()
        
        # Crear el enlace HTML con el estilo de texto normal
        html = f"""
        <a href="data:application/octet-stream;base64,{b64_content}" 
           download="{filename}" 
           style="color: inherit; text-decoration: none; cursor: pointer;">
            {reference}
        </a>
        """
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown(f"{reference} (Archivo no encontrado)")

def main():
    st.set_page_config(
        page_title="Chat Assistant",
        page_icon="🤖",
        initial_sidebar_state="expanded"
    )
    
    # Agregar CSS personalizado
    st.markdown("""
        <style>
        [data-testid="stButton"] button {
            font-size: 0.8em;
            height: auto;
            padding: 0.2rem 0.6rem;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Inicializar
    db.init_db()
    init_chat_state()
    
    # Sidebar
    with st.sidebar:
        st.title("💬 Chats")
        
        # Selector de base de datos
        st.subheader("📚 Base de Datos")
        databases = doc_db.get_document_databases()
        db_options = [db['name'] for db in databases]
        
        # Seleccionar la primera base de datos por defecto
        default_index = db_options.index(st.session_state.current_document_db) if st.session_state.current_document_db else 0
        selected_db = st.selectbox(
            "Base de datos de documentos:",
            db_options,
            index=default_index
        )
        
        if selected_db != st.session_state.current_document_db:
            st.session_state.current_document_db = selected_db
            st.session_state.agents["cag"].set_database(selected_db)
            st.rerun()
        
        st.divider()
        
        # Botón de nueva conversación
        if st.button("➕ Nueva conversación", use_container_width=True):
            st.session_state.current_conversation_id = db.create_conversation()
            st.session_state.agents["conversational"].set_conversation_id(
                st.session_state.current_conversation_id
            )
            st.rerun()
        
        st.divider()
        
        # Lista de conversaciones
        conversations = db.get_conversations()
        for conv_id, title, created_at in conversations:
            col1, col2 = st.columns([4,1])
            
            with col1:
                # Limitar el título a 20 caracteres y agregar ellipsis si es necesario
                display_title = title[:20] + "..." if len(title) > 20 else title
                if st.button(
                    f"{'📍' if conv_id == st.session_state.current_conversation_id else '💭'} {display_title}",
                    key=f"chat_{conv_id}",
                    use_container_width=True,
                    help=title  # Mostrar título completo al hacer hover
                ):
                    st.session_state.current_conversation_id = conv_id
                    st.session_state.agents["conversational"].set_conversation_id(conv_id)
                    st.rerun()
            
            with col2:
                if st.button("🗑️", key=f"delete_{conv_id}"):
                    db.delete_conversation(conv_id)
                    db.delete_conversation_memory(conv_id)
                    if conv_id == st.session_state.current_conversation_id:
                        st.session_state.current_conversation_id = db.create_conversation()
                        st.session_state.agents["conversational"].set_conversation_id(
                            st.session_state.current_conversation_id
                        )
                    st.rerun()
    
    # Área principal de chat
    st.title("🤖 Chat Assistant")
    
    messages = db.get_messages(st.session_state.current_conversation_id)
    for message in messages:
        icon = "🤖" if message["role"] == "assistant" else "👤"
        with st.chat_message(message["role"], avatar=icon):
            # Manejar tanto mensajes antiguos como nuevos
            content = message["content"]
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass
            
            if isinstance(content, dict):
                st.markdown(content["response"])
                if content.get("references"):
                    with st.expander("📚 Referencias utilizadas"):
                        for ref in content["references"]:
                            format_reference_with_download(ref, st.session_state.current_document_db)
                            
                if content.get("metrics"):
                    # Filtrar las métricas, excluyendo 'preparación'
                    filtered_metrics = {
                        k: v for k, v in content['metrics'].items() 
                        if k != 'preparación'
                    }
                    
                    # Mover el tipo al final
                    tipo = filtered_metrics.pop('tipo', '')
                    metrics_text = " | ".join([
                        f"{k}: {v}" for k, v in filtered_metrics.items()
                    ])
                    
                    if tipo:
                        metrics_text += f" | {tipo}"
                    
                    st.markdown(
                        f"<div style='text-align: right; color: #666; font-size: 0.8em'>{metrics_text}</div>", 
                        unsafe_allow_html=True
                    )
            else:
                st.write(content)
    
    # Campo de entrada
    if prompt := st.chat_input("Mensaje..."):
        # Verificar si se ha seleccionado una base de datos
        if not st.session_state.current_document_db:
            st.error("Por favor, selecciona una base de datos de documentos primero.")
            return
            
        with st.chat_message("user", avatar="👤"):
            st.write(prompt)
        db.save_message(st.session_state.current_conversation_id, "user", prompt)
        
        # Usar el agente conversacional para procesar la consulta
        result = st.session_state.agents["conversational"].process_user_query(prompt)
        
        with st.chat_message("assistant", avatar="🤖"):
            if isinstance(result, dict):
                # Asegurarse de que el resultado es un diccionario Python y no una cadena JSON
                if isinstance(result, str):
                    result = json.loads(result)
                
                # Mostrar la respuesta principal
                st.markdown(result['response'])
                
                # Mostrar referencias si existen
                if result.get('references'):
                    with st.expander("📚 Referencias utilizadas"):
                        for ref in result['references']:
                            format_reference_with_download(ref, st.session_state.current_document_db)
                
                # Mostrar métricas si existen
                if result.get('metrics'):
                    # Filtrar las métricas, excluyendo 'preparación'
                    filtered_metrics = {
                        k: v for k, v in result['metrics'].items() 
                        if k != 'preparación'
                    }
                    
                    # Mover el tipo al final
                    tipo = filtered_metrics.pop('tipo', '')
                    metrics_text = " | ".join([
                        f"{k}: {v}" for k, v in filtered_metrics.items()
                    ])
                    
                    if tipo:
                        metrics_text += f" | {tipo}"
                    
                    st.markdown(
                        f"<div style='text-align: right; color: #666; font-size: 0.8em'>{metrics_text}</div>", 
                        unsafe_allow_html=True
                    )
            else:
                st.write(result)
        
        # Guardar el mensaje en la base de datos
        if isinstance(result, dict):
            db.save_message(
                st.session_state.current_conversation_id, 
                "assistant", 
                json.dumps(result)  # Convertir el diccionario a JSON string antes de guardarlo
            )
        else:
            db.save_message(st.session_state.current_conversation_id, "assistant", result)
        
        st.rerun()

if __name__ == "__main__":
    main() 