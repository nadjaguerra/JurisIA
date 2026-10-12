import argparse
import json
from pathlib import Path

from .config import STJ_DATASETS


def main():
    parser = argparse.ArgumentParser(description="JurisIA: STJ, recuperação e RAG")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="Baixar recursos do catálogo oficial")
    sync.add_argument("--dataset", choices=STJ_DATASETS, action="append")
    sub.add_parser("prepare", help="Importar arquivos raw para SQLite")
    index = sub.add_parser("index", help="Criar embeddings e Chroma")
    index.add_argument("--limit", type=int, default=2000,
                       help="Documentos para teste; 0 indexa todos")
    index.add_argument("--size", type=int, default=70)
    index.add_argument("--overlap", type=int, default=15)
    query = sub.add_parser("ask", help="Pesquisar e opcionalmente gerar resposta")
    query.add_argument("question")
    query.add_argument("--k", type=int, default=5)
    query.add_argument("--no-gemini", action="store_true")
    evaluation = sub.add_parser("evaluate", help="Avaliar IDs relevantes rotulados")
    evaluation.add_argument("csv", type=Path)
    evaluation.add_argument("--k", type=int, default=5)
    evaluation.add_argument("--mode", choices=["rerank", "vector"], default="rerank")
    args = parser.parse_args()
    if args.command == "sync":
        from .download import sync as run
        result = run(args.dataset)
    elif args.command == "prepare":
        from .prepare import import_all
        result = import_all()
    elif args.command == "index":
        from .search import index as run
        result = run(args.limit, args.size, args.overlap)
    elif args.command == "ask":
        from .rag import ask
        result = ask(args.question, k=args.k, with_gemini=not args.no_gemini)
        print(result["answer"])
        for i, hit in enumerate(result["hits"], 1):
            doc = hit["document"]
            print(f"[D{i}] {doc.get('process_class')} {doc.get('process_number')} "
                  f"({doc.get('court_body')}, {doc.get('decision_date')}) "
                  f"ID={hit['id']} similaridade={hit['similarity']:.3f}")
        return
    else:
        from .evaluation import evaluate, save
        result = evaluate(args.csv, args.k, args.mode)
        destination = Path("reports") / f"evaluation_{args.mode}.json"
        save(result, destination)
        print(f"Relatório: {destination}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
