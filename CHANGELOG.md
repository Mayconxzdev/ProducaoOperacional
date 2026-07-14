# Histórico de versões

## [2.3.9] - 2026-07-14

- A TV/Foco recebeu um preset Full HD de leitura: pesos de colunas e fontes individuais evitam que OP, status, cliente, modelo, voltagem, entrega e setor sejam cortados.
- O modo Demonstração passa a apresentar as 10 OPs fictícias com esse preset e atualiza somente o layout visual nas instalações existentes, sem apagar o que foi praticado.
- Incluído teste de interface que mede os textos visíveis em uma tela 1920×1080 e falha se qualquer célula precisar ser renderizada com reticências.

## [2.3.8] - 2026-07-14

- Novo ícone de produto baseado no fluxo de três etapas da operação, disponível no executável, nas janelas, nos atalhos e no instalador.
- O empacotamento inclui os assets visuais necessários para que o ícone também apareça na aplicação congelada.
- Corrigido o caminho do ícone na aplicação empacotada pelo PyInstaller.

## [2.3.7] - 2026-07-14

- O instalador oferece três perfis explícitos: Escritório, TV/Foco e Demonstração.
- A Demonstração é totalmente local, inicia com dez OPs fictícias e não consulta NAS, SMTP, cache ou configuração operacional.
- O perfil escolhido é salvo na estação para que o atalho principal mantenha o comportamento correto.

## [2.3.6] - 2026-07-14

- Adicionado guia de uso, restauração segura dos dados fictícios e atalho próprio para Demonstração.
- A personalização de setores passou a usar cartões coloridos persistentes, com contraste e estado visíveis.
- O modo Escritório passou a aceitar tema do sistema, claro ou escuro, salvo localmente por estação.

## [2.3.5] - 2026-07-13

- Importação de PDF, DOCX e ODT mais tolerante a campos fragmentados, datas e tensões em formatos variados.
- Campos de data aceitam entrada com ou sem separadores e normalizam o valor automaticamente.
- Setores ganharam cor de texto independente, prévia e sugestão de contraste.

## [2.3.0] - 2026-07-13

- Evolução da TV/Foco com paginação, personalização por coluna, prévia ampliada e atualização sem reiniciar a tela.
- Aprimoramentos de estabilidade para SQLite, migrações com backup, cache local e tratamento de falhas de rede.
