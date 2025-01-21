# CodeExpert - Intelligent Code Analysis & Repository Management

<!-- ![CodeExpert Banner](https://your-banner-url.png) -->

CodeExpert transforms GitHub repositories into interactive knowledge bases, enabling natural conversations about code. By leveraging advanced RAG (Retrieval-Augmented Generation) and LLM technology, it helps developers understand complex codebases quickly and efficiently.

## 🌟 Features

- **Repository Processing**: Analyze any public GitHub repository
- **Interactive Code Chat**: Ask questions about code in natural language
- **Dual RAG System**: Choose between Base and Filtered RAG for optimal responses
- **Real-time Metrics**: Monitor response quality and relevance
- **Modern UI**: Clean, intuitive interface with real-time progress tracking

## 🚀 Live Demo

Try CodeExpert: [Live Demo](https://www.youtube.com/watch?v=IwigOf-YjO4)

## 🛠️ Technologies Used

- **Frontend**: Streamlit
- **Code Retrieval**: Snowflake Cortex Search
- **Language Model**: Mistral LLM
- **Evaluation**: Custom
- **Data Storage**: Snowflake
- **Version Control**: Git/GitHub

## 📊 Performance Metrics

Our Filtered RAG system achieves significant improvements over the base implementation:

- **Groundedness**: 0.95 (+35.71%)
- **Answer Relevance**: 0.64 (+23%)
- **Response Quality**: 0.64 (+27%)
- **Code References**: Increased from 6 to 34
- **Technical Terms**: Expanded from 4 to 33

## 🔧 Installation & Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/code-expert.git
cd code-expert
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file in the root directory with:
```env
GITHUB_TOKEN=your_github_token
SNOWFLAKE_ACCOUNT=your_snowflake_account
SNOWFLAKE_USER=your_snowflake_user
SNOWFLAKE_PASSWORD=your_snowflake_password
```

5. Run the application:
```bash
streamlit run app.py
```

## 🏗️ Project Structure

```
code-search-rag/
├── app.py                  # Entry point
├── app/
│   ├── main.py            # Main application code
│   ├── core/
│   │   └── config.py      # Configuration settings
│   └── services/
│       ├── github.py      # GitHub integration
│       ├── repository_ingestion.py  # Repository processing
│       └── snowflake.py   # Snowflake integration
├── evaluations/
│   └── trulens_eval.py    # RAG evaluation
└── requirements.txt
```

## 📝 Usage

1. Visit the application URL or run locally
2. Enter a public GitHub repository URL
3. Wait for the processing to complete
4. Select the processed repository from the dropdown
5. Choose between Base RAG or Filtered RAG
6. Start asking questions about the codebase

## 🎯 Key Features in Detail

### Repository Processing
- Intelligent file filtering
- Context-aware code chunking
- Efficient batch processing
- Progress tracking

### RAG Implementation
- Base RAG for standard retrieval
- Filtered RAG for enhanced accuracy
- Real-time performance metrics
- TruLens evaluation integration

### User Interface
- Clean, modern design
- Real-time processing indicators
- Interactive metrics visualization
- Seamless repository management

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Streamlit for the amazing web framework
- Snowflake for Cortex Search capabilities
- Mistral for the powerful LLM
- TruLens for evaluation metrics

## 🔮 Future Plans

- IDE integration
- Automated documentation generation
- Team collaboration features
- Advanced language support
- Real-time code review assistance
- Custom knowledge base creation
- Performance optimization
- Enhanced context understanding

## 📞 Contact

For questions or feedback, please open an issue or contact [divyakasa.edu@gmail.com]

---

Made with  by [Divya Kasa]