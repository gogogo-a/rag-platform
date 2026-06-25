"""Prompt management service."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from internal.model.prompt import PromptModel


PROMPT_AGENT_OPTIONS: List[Dict[str, str]] = [
    {"agent_key": "single", "agent_name": "普通主 Agent", "category": "普通主 Agent"},
    {"agent_key": "supervisor", "agent_name": "专家模式主 Agent", "category": "专家主控 Agent"},
    {"agent_key": "knowledge", "agent_name": "知识专家", "category": "子 Agent"},
    {"agent_key": "search", "agent_name": "搜索专家", "category": "子 Agent"},
    {"agent_key": "location", "agent_name": "位置出行专家", "category": "子 Agent"},
    {"agent_key": "email", "agent_name": "邮件专家", "category": "子 Agent"},
]


def _fake_equals(field_name: str, expected: Any):
    return lambda item: getattr(item, field_name, None) == expected


def _fake_contains_any(field_names: List[str], keyword: str):
    lowered = keyword.lower()
    return lambda item: any(lowered in str(getattr(item, field_name, "") or "").lower() for field_name in field_names)


class PromptService:
    """Read and update prompts stored in MongoDB."""

    def default_prompt_seeds(self) -> List[Dict[str, str]]:
        return []

    async def ensure_defaults(self) -> None:
        for seed in self.default_prompt_seeds():
            existing = await self._find_one_by(agent_key=seed["agent_key"])
            if existing:
                continue
            await PromptModel(
                **seed,
                is_active=True,
                is_copy=False,
                version_name="默认版本",
            ).insert()

    async def list_prompts(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        agent_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.ensure_defaults()
        conditions = []
        if category:
            conditions.append(self._condition("category", category))
        if agent_key:
            conditions.append(self._condition("agent_key", agent_key))
        if keyword:
            conditions.append(
                self._text_condition(["agent_key", "agent_name", "category", "version_name", "content"], keyword)
            )

        query = PromptModel.find(*conditions).sort("-updated_at")
        total = await query.count()
        rows = await query.skip((page - 1) * page_size).limit(page_size).to_list()
        return {
            "items": [self._to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_active_prompt(self, agent_key: str) -> str:
        await self.ensure_defaults()
        prompt = await self._find_one_by(agent_key=agent_key, is_active=True)
        if prompt:
            return prompt.content

        raise ValueError("Prompt不存在")

    async def update_prompt(self, prompt_uuid: str, content: str, save_copy: bool = False) -> Dict[str, Any]:
        prompt = await self._get_by_uuid(prompt_uuid)
        if not content or not content.strip():
            raise ValueError("Prompt内容不能为空")

        now = datetime.now()
        if save_copy:
            await self._deactivate_agent_prompts(prompt.agent_key)
            copy_prompt = PromptModel(
                agent_key=prompt.agent_key,
                agent_name=prompt.agent_name,
                category=prompt.category,
                content=content.strip(),
                is_active=True,
                is_copy=True,
                source_uuid=prompt.uuid,
                version_name=f"{now.strftime('%Y%m%d%H%M%S')}-{prompt.agent_name}",
                created_at=now,
                updated_at=now,
            )
            await copy_prompt.insert()
            return self._to_dict(copy_prompt)

        prompt.content = content.strip()
        prompt.updated_at = now
        await prompt.save()
        return self._to_dict(prompt)

    async def activate_prompt(self, prompt_uuid: str) -> Dict[str, Any]:
        prompt = await self._get_by_uuid(prompt_uuid)
        await self._deactivate_agent_prompts(prompt.agent_key)
        prompt.is_active = True
        prompt.updated_at = datetime.now()
        await prompt.save()
        return self._to_dict(prompt)

    async def ensure_prompt_for_agent(self, agent_key: str, agent_name: str, content: str = "") -> Dict[str, Any]:
        existing = await self._find_one_by(agent_key=agent_key)
        if existing:
            return self._to_dict(existing)

        now = datetime.now()
        prompt = PromptModel(
            agent_key=agent_key,
            agent_name=agent_name,
            category="子 Agent",
            content=content.strip() or f"你是{agent_name}，请根据可用工具和用户问题给出清晰、准确的回答。",
            is_active=True,
            is_copy=False,
            version_name="默认版本",
            created_at=now,
            updated_at=now,
        )
        await prompt.insert()
        return self._to_dict(prompt)

    def get_options(self) -> Dict[str, Any]:
        categories = []
        options = list(PROMPT_AGENT_OPTIONS)
        for option in options:
            if option["category"] not in categories:
                categories.append(option["category"])
        return {
            "agents": options,
            "categories": categories,
        }

    async def get_agent_options(self) -> List[Dict[str, str]]:
        await self.ensure_defaults()
        rows = await PromptModel.find().sort("agent_key", "-updated_at").to_list()
        options: List[Dict[str, str]] = []
        seen = set()
        for row in rows:
            if row.agent_key in seen:
                continue
            seen.add(row.agent_key)
            options.append({
                "agent_key": row.agent_key,
                "agent_name": row.agent_name,
                "category": row.category,
            })
        for option in PROMPT_AGENT_OPTIONS:
            if option["agent_key"] not in seen:
                options.append(option)
        return options

    async def _get_by_uuid(self, prompt_uuid: str):
        prompt = await self._find_one_by(uuid=prompt_uuid)
        if not prompt:
            raise ValueError("Prompt不存在")
        return prompt

    async def _deactivate_agent_prompts(self, agent_key: str) -> None:
        rows = await PromptModel.find(self._condition("agent_key", agent_key), self._condition("is_active", True)).to_list()
        for row in rows:
            row.is_active = False
            row.updated_at = datetime.now()
            await row.save()

    def _condition(self, field_name: str, expected: Any):
        field = getattr(PromptModel, field_name, None)
        if field is None:
            return _fake_equals(field_name, expected)
        try:
            return field == expected
        except Exception:
            return _fake_equals(field_name, expected)

    def _text_condition(self, field_names: List[str], keyword: str):
        if not hasattr(PromptModel, field_names[0]):
            return _fake_contains_any(field_names, keyword)
        return {
            "$or": [
                {field_name: {"$regex": keyword, "$options": "i"}}
                for field_name in field_names
            ]
        }

    async def _find_one_by(self, **kwargs):
        conditions = [self._condition(field_name, expected) for field_name, expected in kwargs.items()]
        return await PromptModel.find_one(*conditions)

    def _to_dict(self, prompt) -> Dict[str, Any]:
        return {
            "id": str(getattr(prompt, "id", "") or ""),
            "uuid": prompt.uuid,
            "agent_key": prompt.agent_key,
            "agent_name": prompt.agent_name,
            "category": prompt.category,
            "content": prompt.content,
            "is_active": prompt.is_active,
            "is_copy": prompt.is_copy,
            "source_uuid": prompt.source_uuid,
            "version_name": prompt.version_name,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        }


prompt_service = PromptService()
