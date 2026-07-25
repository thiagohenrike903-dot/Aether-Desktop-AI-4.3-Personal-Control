# Próximas ideias para o Aether

A versão 4.3 entregou personalização, foco, linha do tempo, comparação A/B,
cofre por integração, políticas por projeto, auditoria investigável, Model Lab,
workflows, biblioteca incremental, backup, privacidade, verificação, saúde,
ensaio, avaliações e governança. As próximas versões devem aprofundar os pontos
que ainda possuem limitações reais.

## Prioridade alta

### 1. Runtime autônomo

- Incorporar uma distribuição Python verificada ao instalador.
- Preparar OCR e dependências opcionais por componentes selecionáveis.
- Permitir primeira execução integralmente offline.
- Diagnosticar arquitetura, espaço e compatibilidade antes da instalação.

### 2. Isolamento de plugins

- Executar cada plugin em processo separado com ambiente mínimo.
- Manifesto de arquivos, rede, subprocessos e recursos solicitados.
- Assinatura e hash do pacote instalado.
- Encerramento real, limite de CPU/memória e revogação imediata.

### 3. Instalação de atualização assinada

- Baixar o artefato por transporte pinado.
- Revalidar Ed25519, SHA-256, plataforma e arquitetura.
- Criar snapshot automaticamente antes de aplicar.
- Trocar arquivos de forma transacional e reverter se a verificação pós-início
  falhar.

### 4. Auditoria com âncora externa

- Assinar periodicamente o hash da cabeça da cadeia com uma chave do sistema.
- Permitir exportar a âncora para mídia ou serviço separado.
- Detectar exclusão total e recálculo da cadeia local.
- Política de retenção e verificação independente.

### 5. Navegador persistente seguro

- Processo de navegador isolado por perfil.
- Proxy de saída com DNS/IP pinado por conexão.
- Allowlist de downloads, uploads, esquemas e domínios.
- Sessões visíveis e revogáveis, com replay redigido da auditoria.

## Produto e experiência

### 6. Cliente móvel/PWA

- PWA autenticada para chat, projetos, memória e acompanhamento de operações.
- Pareamento local por QR e chaves revogáveis.
- Aprovações remotas com detalhes completos e expiração curta.
- Recursos exclusivamente desktop claramente indisponíveis no celular.

### 7. Gerenciador de modelos locais

- Catálogo de modelos compatíveis sem download silencioso.
- Verificação de hash/licença antes de instalar.
- Estimativa de RAM, VRAM e desempenho no computador atual.
- Migração e remoção segura do cache.

### 8. Avaliações executáveis

- Executar os casos pessoais contra perfis, prompts, skills e builds
  selecionados.
- Congelar contexto e versão de cada dependência.
- Repetições estatísticas para reduzir variação.
- Aprovação explícita antes de gerar custo externo.

### 9. Verificação de resposta avançada

- Resolver citações no nível de frase.
- Detectar contradições entre fontes independentes.
- Reexecutar consultas cuja fonte esteja desatualizada.
- Presets por domínio, como jurídico, saúde, finanças e pesquisa acadêmica.

### 10. Biblioteca multimodal local

- OCR por layout, imagens, tabelas e gráficos com origem visual.
- Áudio e vídeo com timestamps.
- Comparação de versões com diff por página, parágrafo, planilha e célula.
- Política de retenção de embeddings e reprocessamento por modelo.

## Regra para novos agentes

Um novo agente só entra quando:

1. possui função não coberta claramente por uma ferramenta ou skill;
2. documenta entrada, saída, permissões, dependências e erros;
3. passa por solicitações reais de avaliação;
4. retorna estado indisponível em vez de sucesso genérico;
5. demonstra ganho mensurável de qualidade ou velocidade;
6. aparece na interface somente quando estiver funcional.

Os agentes existentes podem continuar roteáveis quando sua implementação é
real, mas a interface não deve inventar que uma avaliação comparativa formal já
foi concluída.
