"""
Service para gerenciar Time Zones com sincronização ao iDFace
Responsável por criar, atualizar e deletar time zones sincronizando com o dispositivo iDFace
"""
from typing import Optional, List, Dict, Any
from app.utils.idface_client import idface_client
from fastapi import HTTPException, status


class TimeZoneService:
    """Service para operações de Time Zone com sincronização bidirecional"""
    
    # ==================== Create Operations ====================
    
    @staticmethod
    async def create_time_zone_with_sync(
        db,
        name: str,
        time_spans_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Cria um time zone e ASSOCIA AUTOMATICAMENTE aos portais existentes via AccessRule
        """
        new_tz = None
        new_access_rule = None
        
        try:
            # 1. Criar time zone no banco de dados local
            new_tz = await db.timezone.create(data={"name": name})
            
            # 2. Sincronizar com o iDFace
            idface_id = None
            try:
                async with idface_client:
                    tz_payload = {"name": name}
                    result_tz = await idface_client.create_time_zone(tz_payload)
                    
                    if not result_tz.get("ids"):
                        raise ValueError("Falha ao obter ID do iDFace para o time zone.")
                    
                    idface_id = result_tz["ids"][0]
                    
                    await db.timezone.update(
                        where={"id": new_tz.id},
                        data={"idFaceId": idface_id}
                    )
                    
                    # 3. Criar e sincronizar time spans, se houver
                    if time_spans_data:
                        for span_data in time_spans_data:
                            local_span = await db.timespan.create(
                                data={
                                    "timeZoneId": new_tz.id,
                                    **span_data
                                }
                            )
                            
                            span_payload = TimeZoneService._prepare_span_payload_for_idface(
                                idface_id,
                                span_data
                            )
                            result_span = await idface_client.create_time_span(span_payload)
                            
                            if result_span.get("ids"):
                                span_idface_id = result_span["ids"][0]
                                await db.timespan.update(
                                    where={"id": local_span.id},
                                    data={"idFaceId": span_idface_id}
                                )
            
            except Exception as sync_error:
                if new_tz:
                    await db.timezone.delete(where={"id": new_tz.id})
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erro ao sincronizar com iDFace: {str(sync_error)}"
                )
            
            # ✅ 4. NOVO: CRIAR ACCESS RULE AUTOMÁTICA PARA O TIME ZONE
            access_rule_name = f"Access Rule for TimeZone: {name}"
            new_access_rule = await db.accessrule.create(
                data={
                    "name": access_rule_name,
                    "type": 1,
                    "priority": 5
                }
            )
            
            # Sincronizar AccessRule com iDFace
            try:
                async with idface_client:
                    ar_result = await idface_client.create_access_rule({
                        "name": access_rule_name,
                        "type": 1,
                        "priority": 5
                    })
                    
                    ar_ids = ar_result.get("ids", [])
                    if ar_ids:
                        new_access_rule = await db.accessrule.update(
                            where={"id": new_access_rule.id},
                            data={"idFaceId": ar_ids[0]}
                        )
            except Exception as e:
                print(f"Aviso: Erro ao sincronizar AccessRule: {e}")
            
            # 5. Vincular TimeZone à AccessRule
            await db.accessruletimezone.create(
                data={
                    "accessRuleId": new_access_rule.id,
                    "timeZoneId": new_tz.id
                }
            )
            
            # Sincronizar vínculo no iDFace
            if new_access_rule.idFaceId and idface_id:
                try:
                    async with idface_client:
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "access_rule_time_zones",
                                "values": [{
                                    "access_rule_id": new_access_rule.idFaceId,
                                    "time_zone_id": idface_id
                                }]
                            }
                        )
                except Exception as e:
                    print(f"Aviso: Erro ao sincronizar TimeZone-AccessRule: {e}")
            
            # ✅ 6. NOVO: ASSOCIAR AUTOMATICAMENTE A TODOS OS PORTAIS
            all_portals = await db.portal.find_many()
            
            portals_associated = 0
            for portal in all_portals:
                try:
                    # Criar vínculo local Portal-AccessRule
                    await db.portalaccessrule.create(
                        data={
                            "portalId": portal.id,
                            "accessRuleId": new_access_rule.id
                        }
                    )
                    portals_associated += 1
                    
                    # Sincronizar Portal-AccessRule no iDFace
                    if portal.idFaceId and new_access_rule.idFaceId:
                        try:
                            async with idface_client:
                                await idface_client.request(
                                    "POST",
                                    "create_objects.fcgi",
                                    json={
                                        "object": "portal_access_rules",
                                        "values": [{
                                            "portal_id": portal.idFaceId,
                                            "access_rule_id": new_access_rule.idFaceId
                                        }]
                                    }
                                )
                                print(f"✅ Portal '{portal.name}' → AccessRule (TimeZone '{name}')")
                        except Exception as e:
                            print(f"Aviso: Erro ao sincronizar Portal-AccessRule: {e}")
                    
                    # ✅ ADICIONAL: Vincular Portal diretamente ao TimeZone no iDFace
                    if portal.idFaceId and idface_id:
                        try:
                            async with idface_client:
                                # Criar vínculo portal_time_zones no iDFace
                                await idface_client.request(
                                    "POST",
                                    "create_objects.fcgi",
                                    json={
                                        "object": "portal_time_zones",
                                        "values": [{
                                            "portal_id": portal.idFaceId,
                                            "time_zone_id": idface_id
                                        }]
                                    }
                                )
                                print(f"✅ Portal '{portal.name}' → TimeZone (direto)")
                        except Exception as e:
                            # Vínculo direto pode não existir, não é crítico
                            print(f"Info: Vínculo direto Portal-TimeZone: {e}")
                
                except Exception as e:
                    print(f"Aviso: Erro ao associar portal {portal.id}: {e}")
            
            print(f"✅ TimeZone criado e associado a {portals_associated} portal(is)")
            
            # Recarregar com os dados completos
            result = await db.timezone.find_unique(
                where={"id": new_tz.id},
                include={"timeSpans": True}
            )
            return result
        
        except Exception as e:
            # Rollback em caso de erro
            if new_access_rule:
                try:
                    await db.accessrule.delete(where={"id": new_access_rule.id})
                except:
                    pass
            
            if new_tz and not getattr(new_tz, 'idFaceId', None):
                try:
                    await db.timezone.delete(where={"id": new_tz.id})
                except:
                    pass
            
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao criar time zone: {str(e)}"
            )
    
    # ==================== Update Operations ====================
    
    @staticmethod
    async def update_time_zone_with_sync(
        db,
        tz_id: int,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Atualiza um time zone no banco local e sincroniza com o iDFace.
        
        Args:
            db: Instância do banco de dados Prisma
            tz_id: ID do time zone a atualizar
            name: Novo nome (opcional)
            
        Returns:
            Dicionário com dados atualizados do time zone
            
        Raises:
            HTTPException: Se houver erro na atualização ou sincronização
        """
        # Verificar se time zone existe
        existing_tz = await db.timezone.find_unique(where={"id": tz_id})
        if not existing_tz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Time zone {tz_id} não encontrado"
            )
        
        # Preparar dados de atualização
        update_data = {}
        if name is not None:
            update_data["name"] = name
        
        if not update_data:
            # Sem mudanças, retornar dados atuais
            return await db.timezone.find_unique(
                where={"id": tz_id},
                include={"timeSpans": True}
            )
        
        try:
            # 1. Atualizar no banco local
            updated_tz = await db.timezone.update(
                where={"id": tz_id},
                data=update_data,
                include={"timeSpans": True}
            )
            
            # 2. Sincronizar com iDFace, se houver idFaceId
            if existing_tz.idFaceId:
                try:
                    async with idface_client:
                        # Atualizar no iDFace
                        await idface_client.update_time_zone(
                            existing_tz.idFaceId,
                            update_data
                        )
                except Exception as sync_error:
                    # Log do erro mas não falha a operação
                    # (time zone foi atualizado localmente)
                    print(f"Aviso: Falha ao sincronizar atualização com iDFace: {sync_error}")
            
            return updated_tz
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao atualizar time zone: {str(e)}"
            )
    
    @staticmethod
    async def update_time_span_with_sync(
        db,
        span_id: int,
        start: Optional[int] = None,
        end: Optional[int] = None,
        days_and_holidays: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """
        Atualiza um time span no banco local e sincroniza com o iDFace.
        
        Args:
            db: Instância do banco de dados Prisma
            span_id: ID do time span a atualizar
            start: Novo horário de início em segundos (opcional)
            end: Novo horário de término em segundos (opcional)
            days_and_holidays: Dicionário com dias da semana e feriados (opcional)
            
        Returns:
            Dicionário com dados atualizados do time span
            
        Raises:
            HTTPException: Se houver erro na atualização ou sincronização
        """
        # Verificar se time span existe
        existing_span = await db.timespan.find_unique(where={"id": span_id})
        if not existing_span:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Time span {span_id} não encontrado"
            )
        
        # Preparar dados de atualização
        update_data = {}
        if start is not None:
            update_data["start"] = start
        if end is not None:
            update_data["end"] = end
        if days_and_holidays:
            update_data.update(days_and_holidays)
        
        if not update_data:
            # Sem mudanças, retornar dados atuais
            return existing_span
        
        # Validar intervalo se ambos start e end foram fornecidos
        final_start = update_data.get("start", existing_span.start)
        final_end = update_data.get("end", existing_span.end)
        
        if final_start >= final_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Horário de início deve ser menor que horário de fim"
            )
        
        try:
            # 1. Atualizar no banco local
            updated_span = await db.timespan.update(
                where={"id": span_id},
                data=update_data
            )
            
            # 2. Buscar o time zone associado para sincronização
            tz = await db.timezone.find_unique(
                where={"id": existing_span.timeZoneId}
            )
            
            # 3. Sincronizar com iDFace, se houver idFaceId no time zone
            if tz and tz.idFaceId and existing_span.idFaceId:
                try:
                    async with idface_client:
                        # Preparar dados do span para o iDFace (sem time_zone_id)
                        span_update_data = {
                            "start": final_start,
                            "end": final_end,
                            "sun": 1 if update_data.get("sun", existing_span.sun) else 0,
                            "mon": 1 if update_data.get("mon", existing_span.mon) else 0,
                            "tue": 1 if update_data.get("tue", existing_span.tue) else 0,
                            "wed": 1 if update_data.get("wed", existing_span.wed) else 0,
                            "thu": 1 if update_data.get("thu", existing_span.thu) else 0,
                            "fri": 1 if update_data.get("fri", existing_span.fri) else 0,
                            "sat": 1 if update_data.get("sat", existing_span.sat) else 0,
                            "hol1": 1 if update_data.get("hol1", existing_span.hol1) else 0,
                            "hol2": 1 if update_data.get("hol2", existing_span.hol2) else 0,
                            "hol3": 1 if update_data.get("hol3", existing_span.hol3) else 0,
                        }
                        # Atualizar no iDFace usando o idFaceId do span
                        await idface_client.update_time_span(
                            existing_span.idFaceId,  # ID do time span no iDFace
                            span_update_data
                        )
                except Exception as sync_error:
                    # Log do erro mas não falha a operação
                    print(f"Aviso: Falha ao sincronizar time span com iDFace: {sync_error}")
            else:
                # Time zone ou span sem idFaceId - sincronização não é possível
                print(f"Aviso: Time zone ou span sem idFaceId - sincronização não executada")
            
            return updated_span
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao atualizar time span: {str(e)}"
            )
    
    # ==================== Delete Operations ====================
    
    @staticmethod
    async def delete_time_zone_with_sync(
        db,
        tz_id: int
    ) -> None:
        """
        Deleta um time zone do banco local e sincroniza com o iDFace.
        
        Args:
            db: Instância do banco de dados Prisma
            tz_id: ID do time zone a deletar
            
        Raises:
            HTTPException: Se houver erro na deleção ou sincronização
        """
        # Verificar se time zone existe
        existing_tz = await db.timezone.find_unique(
            where={"id": tz_id},
            include={"timeSpans": True}
        )
        if not existing_tz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Time zone {tz_id} não encontrado"
            )
        
        try:
            # 1. Sincronizar com iDFace primeiro, se houver idFaceId
            if existing_tz.idFaceId:
                try:
                    async with idface_client:
                        # Deletar time spans no iDFace
                        if existing_tz.timeSpans:
                            for span in existing_tz.timeSpans:
                                await idface_client.delete_time_span(span.id)
                        
                        # Deletar time zone no iDFace
                        await idface_client.delete_time_zone(existing_tz.idFaceId)
                except Exception as sync_error:
                    # Log do erro mas ainda deleta localmente
                    print(f"Aviso: Falha ao deletar no iDFace: {sync_error}")
            
            # 2. Deletar localmente (cascata deleta os time spans)
            await db.timezone.delete(where={"id": tz_id})
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao deletar time zone: {str(e)}"
            )
    
    @staticmethod
    async def delete_time_span_with_sync(
        db,
        span_id: int
    ) -> None:
        """
        Deleta um time span do banco local e sincroniza com o iDFace.
        
        Args:
            db: Instância do banco de dados Prisma
            span_id: ID do time span a deletar
            
        Raises:
            HTTPException: Se houver erro na deleção ou sincronização
        """
        # Verificar se time span existe
        existing_span = await db.timespan.find_unique(where={"id": span_id})
        if not existing_span:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Time span {span_id} não encontrado"
            )
        
        try:
            # 1. Buscar o time zone associado
            tz = await db.timezone.find_unique(
                where={"id": existing_span.timeZoneId}
            )
            
            # 2. Sincronizar com iDFace, se houver idFaceId
            if tz and tz.idFaceId:
                try:
                    async with idface_client:
                        # Deletar no iDFace
                        await idface_client.delete_time_span(span_id)
                except Exception as sync_error:
                    # Log do erro mas ainda deleta localmente
                    print(f"Aviso: Falha ao deletar time span no iDFace: {sync_error}")
            
            # 3. Deletar localmente
            await db.timespan.delete(where={"id": span_id})
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao deletar time span: {str(e)}"
            )
    
    # ==================== Helper Methods ====================
    
    @staticmethod
    def _prepare_span_payload_for_idface(
        time_zone_id: int,
        span_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepara o payload de um time span para o iDFace.
        Converte booleanos em inteiros (0 ou 1) conforme esperado pela API.
        
        Args:
            time_zone_id: ID do time zone no iDFace
            span_data: Dicionário com dados do span
            
        Returns:
            Dicionário formatado para a API iDFace
        """
        return {
            "time_zone_id": time_zone_id,
            "start": span_data.get("start", 0),
            "end": span_data.get("end", 86400),
            "sun": 1 if span_data.get("sun", False) else 0,
            "mon": 1 if span_data.get("mon", False) else 0,
            "tue": 1 if span_data.get("tue", False) else 0,
            "wed": 1 if span_data.get("wed", False) else 0,
            "thu": 1 if span_data.get("thu", False) else 0,
            "fri": 1 if span_data.get("fri", False) else 0,
            "sat": 1 if span_data.get("sat", False) else 0,
            "hol1": 1 if span_data.get("hol1", False) else 0,
            "hol2": 1 if span_data.get("hol2", False) else 0,
            "hol3": 1 if span_data.get("hol3", False) else 0,
        }
    
    @staticmethod
    async def sync_time_zone_to_idface(
        db,
        tz_id: int
    ) -> Dict[str, Any]:
        """
        Sincroniza um time zone existente com o iDFace.
        Útil para reenvio de dados após problemas de sincronização.
        
        Args:
            db: Instância do banco de dados Prisma
            tz_id: ID do time zone a sincronizar
            
        Returns:
            Dicionário com resultado da sincronização
            
        Raises:
            HTTPException: Se houver erro na sincronização
        """
        tz = await db.timezone.find_unique(
            where={"id": tz_id},
            include={"timeSpans": True}
        )
        
        if not tz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Time zone {tz_id} não encontrado"
            )
        
        try:
            async with idface_client:
                # 1. Criar time zone no iDFace
                try:
                    tz_payload = {"name": tz.name}
                    result_tz = await idface_client.create_time_zone(tz_payload)
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Falha ao criar time_zone no iDFace. Payload: {tz_payload}. Erro: {e}"
                    )
                
                # 2. Extrair o novo ID do iDFace da resposta
                if not result_tz.get("ids"):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Falha ao obter ID do iDFace para o time zone. Resposta: {result_tz}"
                    )
                
                idface_id = result_tz["ids"][0]
                
                # 3. Salvar o novo idFaceId no banco de dados local
                await db.timezone.update(
                    where={"id": tz_id},
                    data={"idFaceId": idface_id}
                )
                
                # 4. Sincronizar time spans
                if tz.timeSpans:
                    for span in tz.timeSpans:
                        try:
                            span_payload = TimeZoneService._prepare_span_payload_for_idface(
                                idface_id,
                                {
                                    "start": span.start,
                                    "end": span.end,
                                    "sun": span.sun,
                                    "mon": span.mon,
                                    "tue": span.tue,
                                    "wed": span.wed,
                                    "thu": span.thu,
                                    "fri": span.fri,
                                    "sat": span.sat,
                                    "hol1": span.hol1,
                                    "hol2": span.hol2,
                                    "hol3": span.hol3,
                                }
                            )
                            await idface_client.create_time_span(span_payload)
                        except Exception as e:
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"Falha ao criar time_span no iDFace. Payload: {span_payload}. Erro: {e}"
                            )
                
                return {
                    "success": True,
                    "message": "Time zone sincronizado com sucesso",
                    "idFaceId": idface_id,
                    "timeSpansCount": len(tz.timeSpans) if tz.timeSpans else 0
                }
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao sincronizar time zone: {str(e)}"
            )
