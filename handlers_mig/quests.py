@router.callback_query(F.data.startswith("q_choice:"))
async def handle_quest_choice(callback: types.CallbackQuery, quest_service: QuestService):
    # Парсимо дані з кнопки: q_choice:quest_id:choice_index
    _, q_id, c_idx = callback.data.split(":")
    
    error, next_node = await quest_service.process_choice(
        callback.from_user.id, q_id, int(c_idx)
    )

    if error:
        return await callback.answer(error, show_alert=True)

    # Рендеримо наступний вузол
    builder = InlineKeyboardBuilder()
    for i, c in enumerate(next_node.choices):
        builder.button(text=c.text, callback_data=f"q_choice:{q_id}:{i}")
    
    await callback.message.edit_text(next_node.text, reply_markup=builder.as_markup())
