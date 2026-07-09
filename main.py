import os
from pathlib import Path

def create_platform_structure():
    # Definição do diretório raiz
    root = Path("heraclitus-platform")
    
    print(f"🚀 Iniciando a criação do ecossistema: {root.name}/\n")

    # 1. Arquivos globais da raiz
    root_files = {
        "README.md": "# Heraclitus Platform\n\nMonorepo central da plataforma enterprise nacional Heraclitus.",
        "LICENSE": "MIT License\n\nCopyright (c) 2026 Heraclitus Enterprise",
        "ROADMAP.md": "# Product Roadmap\n\n- Phase 1: Engine Core & Ingestion\n- Phase 2: DDD Domains & AI Agents",
        "CHANGELOG.md": "# Changelog\n\nAll notable changes to this project will be documented in this file.",
        "CONTRIBUTING.md": "# Contributing Guide\n\nWelcome to Heraclitus! Please follow DDD guidelines for changes."
    }

    # 2. Lista completa de diretórios comuns da arquitetura unificada
    directories = [
        # CI/CD & Docs
        ".github/workflows",
        "docs/architecture", "docs/specifications", "docs/adr", "docs/api", 
        "docs/compliance", "docs/deployment", "docs/whitepapers",
        
        # Schemas & Contratos Globais
        "schemas/events", "schemas/ledger", "schemas/graph", "schemas/ai", 
        "schemas/contracts", "schemas/public_records",
        
        # Configs & Deployment
        "configs/development", "configs/staging", "configs/production", "configs/docker", "configs/kubernetes",
        "deployment/terraform", "deployment/ansible", "deployment/helm", "deployment/scripts",
        
        # SDKs
        "sdk/rust", "sdk/python", "sdk/go", "sdk/java", "sdk/dotnet", "sdk/javascript", "sdk/cli",
        
        # Core Engine (Baixo Nível)
        "engine/heraclitusdb/storage", "engine/heraclitusdb/wal", "engine/heraclitusdb/ledger",
        "engine/heraclitusdb/replication", "engine/heraclitusdb/consensus", "engine/heraclitusdb/indexes",
        "engine/heraclitusdb/vector", "engine/heraclitusdb/graph", "engine/heraclitusdb/sql",
        "engine/heraclitusdb/optimizer", "engine/heraclitusdb/query", "engine/heraclitusdb/cache",
        "engine/heraclitusdb/compression", "engine/heraclitusdb/crypto", "engine/heraclitusdb/provenance",
        "engine/heraclitusdb/audit", "engine/heraclitusdb/auth", "engine/heraclitusdb/plugins", "engine/heraclitusdb/tests",
        "engine/kernel",
        
        # Platform Cross-Services
        "platform/gateway", "platform/identity", "platform/notification", "platform/search",
        "platform/workflow", "platform/scheduler", "platform/secrets", "platform/telemetry", 
        "platform/billing", "platform/api",
        
        # Runtimes, Apps & Workers
        "apps/portal", "apps/dashboard", "apps/dashboard-executivo", "apps/admin", "apps/mobile", "apps/desktop", "apps/cli",
        "workers/crawler", "workers/crawlers", "workers/ocr", "workers/ocr-processor", "workers/embeddings", 
        "workers/ingestion", "workers/scheduler", "workers/notifications", "workers/reports", "workers/ai", 
        "workers/ai-agent-worker", "workers/cleanup",
        
        # Serviços Legados / Módulos de Suporte
        "services/radar/collectors/pncp", "services/radar/collectors/comprasgov", "services/radar/collectors/dou",
        "services/radar/collectors/estaduais", "services/radar/collectors/municipais", "services/radar/collectors/estatais",
        "services/radar/collectors/custom",
        "services/radar/parser", "services/radar/ocr", "services/radar/deduplication", "services/radar/enrichment",
        "services/radar/normalization", "services/radar/pipeline",
        "services/intelligence/embeddings", "services/intelligence/reranking", "services/intelligence/scoring",
        "services/intelligence/recommendations", "services/intelligence/forecasting", "services/intelligence/pricing",
        "services/intelligence/competitors", "services/intelligence/similarity", "services/intelligence/explainability",
        "services/ai/agents", "services/ai/prompts", "services/ai/rag", "services/ai/memory", "services/ai/tools",
        "services/ai/planner", "services/ai/orchestrator", "services/ai/document_generation", "services/ai/summarization",
        "services/ai/legal", "services/ai/proposal_writer",
        "services/crm", "services/compliance", "services/analytics", "services/graph", "services/contracts",
        "services/pricing", "services/reports",
        
        # Knowledge Data & Datasets
        "knowledge/ontology", "knowledge/taxonomies", "knowledge/embeddings", "knowledge/graph", "knowledge/vectors",
        "knowledge/legal", "knowledge/procurement", "knowledge/templates", "knowledge/prompts",
        "datasets/pncp", "datasets/dou", "datasets/jurisprudence", "datasets/contracts", "datasets/historical",
        "datasets/benchmarks", "datasets/synthetic",
        
        # Global Tests & Utilities
        "tests/unit", "tests/integration", "tests/performance", "tests/security", "tests/stress", "tests/fuzzing",
        "tests/ai", "tests/compliance",
        "benchmarks", "examples", "notebooks", "tools", "scripts", "assets"
    ]

    # 3. Lista de Domínios de Negócio (Camada DDD Dinâmica)
    domains = [
        "procurement", "contracts", "proposals", "organizations", "companies",
        "users", "compliance", "audit", "notifications", "analytics",
        "ai", "graph", "knowledge", "billing", "administration", "intelligence"
    ]

    # Sub-estrutura padrão para Arquitetura Hexagonal dentro de cada domínio
    ddd_subdirs = [
        "domain/models", "domain/exceptions", "domain/events",
        "application/usecases", "application/ports/inbound", "application/ports/outbound",
        "infrastructure/repositories", "infrastructure/adapters", "infrastructure/GroupTests"
    ]

    # --- EXECUÇÃO DA CRIAÇÃO ---

    # Criando os diretórios padrão de infraestrutura/plataforma
    for dir_path in directories:
        target_dir = root / dir_path
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Direcional criado: {target_dir}")

    # Criando e aplicando a anatomia DDD em cada domínio listado
    for domain in domains:
        domain_root = root / "domains" / domain
        domain_root.mkdir(parents=True, exist_ok=True)
        
        # Criando o arquivo README individual do domínio
        readme_content = f"# Domínio de Negócio: {domain.upper()}\n\nEste contexto delimitado segue regras puras de DDD e Arquitetura Hexagonal."
        (domain_root / "README.md").write_text(readme_content, encoding="utf-8")
        
        # Aplicando as subpastas hexagonais
        for sub_dir in ddd_subdirs:
            target_ddd_dir = domain_root / sub_dir
            target_ddd_dir.mkdir(parents=True, exist_ok=True)
            
        print(f"💎 Domínio DDD estruturado com sucesso: domains/{domain}/")

    # Criando os arquivos da raiz
    for filename, content in root_files.items():
        file_path = root / filename
        file_path.write_text(content, encoding="utf-8")
        print(f"📄 Arquivo criado: {file_path}")

    # Criando o exemplo de contrato Protobuf global especificado
    proto_path = root / "schemas" / "events" / "bid_detected.proto"
    proto_content = """syntax = "proto3";
package heraclitus.schemas.events;

message BidDetectedEvent {
  string bid_id = 1;
  string tracking_code = 2; // Código PNCP/Processo
  string buyer_organ = 3;   // Órgão Comprador
  double estimated_value = 4;
  int64 opening_date = 5;
  bytes document_hash = 6;  // SHA-256 para o Ledger do HeraclitusDB
}
"""
    proto_path.write_text(proto_content, encoding="utf-8")
    print(f"🛡️ Contrato de Dados Global injetado: {proto_path}")

    print(f"\n✨ Sucesso Absoluto! A base da plataforma multibilionária foi gerada com sucesso em: ./{root}/")

if __name__ == "__main__":
    create_platform_structure()