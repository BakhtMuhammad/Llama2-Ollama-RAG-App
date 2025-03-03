import streamlit as st
import ollama
from langchain.document_loaders import TextLoader, PyPDFLoader
from langchain.embeddings import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
import tempfile
import os
import shutil

#Define Constants
PERSIST_DIRECTORY = 'llama_rag_db'
COLLECTION_NAME = 'user_documents'
EMBEDDING_MODEL = 'llama2' #The embedding model to use with Ollama
LLM_MODEL = 'llama2' #The LLM model to use with Ollama

#Initialize the session state
if 'messages' not in st.session_state:
    st.session_state.messages = []

#Create the RAG app class
class LlamaRAGApp:
    def __init__(self):
        self.embedding_function = OllamaEmbeddings(model = EMBEDDING_MODEL)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size = 1000,
            chunk_overlap = 200
        )
        self.InitializeDatabase()

    def InitializeDatabase(self):
        if not os.path.exists(PERSIST_DIRECTORY):
            os.makedirs(PERSIST_DIRECTORY)
        self.db = Chroma(
            persist_directory = PERSIST_DIRECTORY,
            embedding_function = self.embedding_function,
            collection_name = COLLECTION_NAME
        )
    def ProcessFile(self, file, file_type):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}') as tmp_file:
                tmp_file.write(file.getbuffer())
                temp_filepath = tmp_file.name
            if file_type == 'txt':
                loader = TextLoader(temp_filepath, encoding='utf-8')
            elif file_type == 'pdf':
                loader = PyPDFLoader(temp_filepath)
            else:
                raise ValueError(f'Unsupported file type:{file_type}')
            documents = loader.load()
            os.unlink(temp_filepath)

            #Split documents into chunks
            docs = self.text_splitter.split_documents(documents)
            return docs
        except Exception as e:
            st.error(f'Error processing file: {str(e)}')
            return None
        
    def AddDocuments(self, docs):
        if docs:
            self.db.add_documents(docs)
            self.db.persist()
            st.success('Document processed and added to the database!')
    
    def ClearDatabase(self):
        try:
            shutil.rmtree(PERSIST_DIRECTORY)
            os.makedirs(PERSIST_DIRECTORY)
            self.InitializeDatabase()
            st.success('Database cleared successfully!')
        except Exception as e:
            st.error(f'Error clearing the database: {str(e)}')
    def Search(self, query, num_results = 4):
        try:
            return self.db.similarity_search(query, k = num_results)
        except Exception as e:
            st.error(f'Error during search: {str(e)}')
            return []
    def GenerateAnswer(self, query, relevant_docs):
        try:
            #Prepare context for the relevant document
            context = '\n\n'.join([doc.page_content for doc in relevant_docs])
            #Create a prompt that includes the retreived context
            prompt = f"""
            you are a helpful AI assistant. Use the following context to answer the question.
            If you don't know the answer based on the context, say "I don't have enough information to answer that."

            Context:
            {context}
            
            Question: {query}

            Answer:
            """
            #Generate respone using Ollama
            response = ollama.generate(model=LLM_MODEL, prompt=prompt)
            return response['response']
        except Exception as e:
            st.error(f'Error generating response: {str(e)}')
            return "I encountered and error while trying to generate an answer"

#Main Application
def main():
    st.title('LLaMA Local Rag Application')

    #Initialize the app
    app = LlamaRAGApp()

    #sidebar for document upload and database management
    st.sidebar.header('Document Management')

    #File upload
    file_type = st.sidebar.selectbox('Select file type:', ['txt', 'pdf'])
    uploaded_file = st.sidebar.file_uploader(f'Upload {file_type} file', type=[file_type])

    if uploaded_file and st.sidebar.button('Process Document'):
        docs = app.ProcessFile(uploaded_file, file_type)
        if docs:
            app.AddDocuments(docs)
    #Database Management
    if st.sidebar.button('Clear Database'):
        app.ClearDatabase()
    
    #Display database statistics
    try:
        collection = app.db.get()
        st.sidebar.subhear('Database Statistics')
        st.sidebar.write(f'Number of documents: {len(collection['ids'])}')
    except Exception as e:
        st.sidebar.error('Error loading database statistics.')
    #Chat interface
    st.header('Chat with your documents')

    #Display the messages
    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            st.write(message['content'])
    #User input
    user_query = st.chat_input('Ask a question about your documents.')
    if user_query:
        #Add user message to the chat history
        st.session_state.messages.append({"role":"user", 'content':user_query})

        #Display user message
        with st.chat_message('user'):
            st.write(user_query)

        #Generate and display the assistant response
        with st.chat_message('assistant'):
            with st.spinner('Thinking...'):
                #Search for relevant documents
                relevant_docs = app.Search(user_query)

                #Generate answer based on relevant documents
                if relevant_docs:
                    response = app.GenerateAnswer(user_query, relevant_docs)
                    st.write(response)

                    #Expand to show resources
                    with st.expander('View Sources'):
                        for i,doc in enumerate(relevant_docs):
                            st.markdown(f'Source {i+1}:')
                            st.write(doc.page_content)
                else:
                    response = "I don't have any relevant information to answer your question. Try uploading some documents of asking a different question."
                    st.write(response)
        #Add assistant message to the chat history
        st.session_state.messages.append({'role':'assistant', 'content':response})
main()