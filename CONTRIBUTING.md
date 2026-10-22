# Contribuindo para o SambaBox

Obrigado pelo interesse em contribuir.

## Fluxo recomendado

1. Abra uma issue descrevendo problema, comportamento esperado e passos de reprodução, **sem credenciais nem dados internos**.
2. Trabalhe em branch `feat/<tema>` ou `fix/<tema>` a partir da `main`.
3. Inclua testes automatizados para a mudança; chamadas a `VBoxManage`, SSH e HTTP devem usar mocks quando apropriado.
4. Execute `py -m unittest discover -v`.
5. Abra pull request explicando comportamento, riscos, testes e impacto de compatibilidade.

## Convenções

- Python com type hints progressivos, classes para recursos de domínio e funções puras para parsing e validação.
- Evite acoplar a interface de terminal com rede, processos, criação de VMs e gerenciamento de credenciais.
- Toda operação destrutiva deve ter confirmação clara e comportamento seguro em caso de falha.
- Não adicione imagens ISO/VMDK/VDI, `.env`, chaves, credenciais ou logs identificáveis ao Git.
- Prefira mudanças pequenas e reversíveis. Não marque etapas de provisionamento como concluídas sem validação do serviço real.

## Licenciamento

Contribuições enviadas ao repositório são oferecidas sob a licença MIT do projeto.
