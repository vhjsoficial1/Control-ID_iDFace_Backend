## 🔄 Sincronizar Portais do iDFace

Se você não tem portais cadastrados no seu banco de dados Prisma, siga os passos abaixo:

### **Opção 1: Via Terminal (Recomendado)**

```bash
# No diretório backend/
python sync_portals.py
```

Isso irá:
1. ✅ Conectar ao dispositivo iDFace
2. ✅ Buscar todas as **áreas/portais** configurados no leitor
3. ✅ Sincronizar automaticamente com a tabela `portals` do banco de dados

**Resultado esperado:**
```
✅ RESULTADO DA SINCRONIZAÇÃO
==============================================================================
✅ Status: SUCESSO
📊 Total sincronizado: 2 portais
   ✨ Criados: 2
   ✏️  Atualizados: 0

📋 Portais sincronizados:
   ✨ ID 1: Entrada (created)
   ✨ ID 2: Saída (created)

📋 PORTAIS CADASTRADOS NO BANCO
==============================================================================
✅ Total de portais no banco: 2
   • Portal 1 (iDFace #1): Entrada
   • Portal 2 (iDFace #2): Saída
```

---

### **Opção 2: Via API HTTP**

**Sincronizar portais:**
```bash
curl -X POST http://localhost:8000/api/v1/sync/portals
```

**Listar portais sincronizados:**
```bash
curl -X GET http://localhost:8000/api/v1/sync/portals
```

---

### **O que acontece internamente?**

1. **Busca no device**: Conecta ao iDFace e executa `load_areas()` para buscar todos os portais
2. **Comparação**: Verifica quais já existem na tabela `portals` do Prisma
3. **Criação**: Insere novos portais (com `idFaceId` do device)
4. **Atualização**: Atualiza nomes se mudaram
5. **Resultado**: Retorna relatório detalhado

---

### **Campos sincronizados:**

```
Database Table: portals
- id              (PK, autoincrement)
- idFaceId        (FK do device, ex: 1, 2, 3)
- name            (nome do portal, ex: "Entrada")
- createdAt       (timestamp)
- updatedAt       (timestamp)
```

---

### **Depois da sincronização:**

✅ Os logs de acesso agora terão portais associados automaticamente!

**Antes (erro):**
```
❌ Portal iDFace #1 não encontrado no banco
```

**Depois (sucesso):**
```
✅ Log salvo com portal: "Entrada" (ID 1)
```

---

### **Se precisar sincronizar novamente:**

Se novos portais forem criados no device, simplesmente execute de novo:

```bash
python sync_portals.py
```

Ele será inteligente e apenas criará/atualizará os que mudaram! 🎯
