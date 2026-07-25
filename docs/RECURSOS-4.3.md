# Aether 4.3 — Personal Control

Esta versão transforma as ideias da 4.2 em sistemas locais conectados ao estado
real do produto. Nenhuma tela deve mostrar dados demonstrativos como se fossem
resultados do núcleo.

## Experiência e identidade

- Painel inicial personalizável por perfil de Trabalho, Estudo ou Pessoal.
- Atalhos, módulos, projetos e automações fixados separadamente em cada perfil.
- Modo foco que recolhe navegação e contexto sem alterar a conversa.
- Largura de leitura, espaçamento, tamanho de código, contraste e tipografia
  salvos por perfil.
- Capas monocromáticas determinísticas para projetos, sem imagens externas.
- Identidade inteiramente preta, branca e cinza, com a logo oficial e o avatar
  Aether preservados.

## Respostas, contexto e comparação

- Linha do tempo recolhível dentro da resposta com eventos operacionais:
  analisado, lido, planejado, fonte consultada, alteração, aprovação, falha e
  cancelamento.
- A linha do tempo não revela raciocínio privado do modelo; ela registra ações,
  fontes e decisões observáveis.
- Comparação A/B lado a lado com diferenças destacadas.
- Métricas discretas de duração, tokens, custo estimado e tempo até o primeiro
  token quando o provedor realmente transmite esse evento.
- Inspetor de contexto com exclusão de memórias e fontes antes de regenerar.
- Verificador local que classifica afirmações como sustentadas, inferências ou
  sem evidência e recusa o rótulo “verificado” quando só há snippets ou uma
  única origem.

## Controle, segurança e privacidade

- Modos globais Normal, Confirmar tudo e Somente leitura.
- Políticas de proteção separadas por projeto.
- Suspensão emergencial de novas automações e execuções de plugins.
- Permissões Perguntar sempre, Permitir nesta sessão ou Bloquear.
- Cofre do sistema operacional com concessões por integração: permanente,
  sessão, temporária ou bloqueada.
- Tokens OAuth de Gmail e Calendar permanecem em memória quando o cofre está
  ativo; não são gravados em arquivos pelo núcleo.
- Perfil 100% local que bloqueia destinos que não sejam loopback.
- Mapa de privacidade por conversa e visão global, contendo somente metadados
  de destino e categorias de dados.
- Auditoria pesquisável por período, ferramenta, projeto, arquivo, site ou
  destinatário, com relatório JSON/Markdown e cadeia SHA-256 interna.

## Sistemas de trabalho

- Central de conexões com estado real, teste mínimo e capacidades offline
  informadas individualmente.
- Model Lab com o mesmo snapshot de contexto para duas respostas, execução
  paralela, métricas e transformação da vencedora em perfil reutilizável.
- Workflows versionados com variáveis tipadas, prévia, aprovações, histórico,
  restauração e conversão de uma operação concluída ainda presente na sessão.
- Modo de ensaio sem efeitos colaterais, comparação do estado dos arquivos e
  invalidação automática quando o estado muda antes da aprovação.
- Biblioteca local com reindexação incremental, duplicatas, versões e índice
  semântico opcional inteiramente local.
- Backup completo selecionável e opcionalmente criptografado de projetos,
  conversas, memórias, skills, automações e configurações. Credenciais ficam
  excluídas por construção.
- Saúde do sistema com histórico, bancos SQLite, integrações, falhas repetidas,
  índices desatualizados e reparos explicitamente reversíveis.
- Avaliações pessoais com exemplos bons/ruins, critérios essenciais e bloqueio
  de ativação quando as métricas fornecidas regredirem.
- Governança de agentes que mantém especialistas incompletos indisponíveis e
  exige contrato, permissões, erros, avaliações reais e ganho mensurável para
  admitir um novo agente.

## Atualização e recuperação

- Canais Estável e Testes.
- Verificação obrigatória de manifesto Ed25519 e artefato SHA-256.
- Snapshots locais com manifesto e hash por arquivo.
- Reversão transacional com snapshot de segurança antes da restauração.
- A instalação automática de atualização ainda não é habilitada; a versão 4.3
  entrega verificação e recuperação sem fingir que existe um instalador remoto.

