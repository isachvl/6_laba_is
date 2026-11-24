import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from analyze import read,rows

def short(value,n=180):
    value=' '.join(str(value).split())
    return value if len(value)<=n else value[:n]+'...'

def value(v):return f'{v:.1f}' if isinstance(v,float) else str(v)
def interval(s):return f"{value(s['median'])} [{value(s['min'])}; {value(s['max'])}]"
def ids(items):return ', '.join(i.removeprefix('user_task_') for i in items) or 'нет'

def main():
    s=read('analysis/summary.json');reviews=read('analysis/reviews.json');config=read('config.json')
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'));pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
    body=ParagraphStyle('body',fontName='Arial',fontSize=8.7,leading=11.1,spaceAfter=5)
    small=ParagraphStyle('small',parent=body,fontSize=7.4,leading=9.2,spaceAfter=4)
    heading=ParagraphStyle('heading',parent=body,fontName='ArialBold',fontSize=11.5,leading=14,spaceBefore=7,spaceAfter=5)
    title=ParagraphStyle('title',parent=heading,fontSize=18,leading=22,spaceAfter=9)
    story=[]
    def p(text,style=body):story.append(Paragraph(escape(str(text)),style))
    def table(data,widths):
        t=Table([[Paragraph(escape(str(c)),small) for c in row] for row in data],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e2edf8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,HexColor('#ccd6e0')),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
        story.extend([t,Spacer(1,5)])
    p('ЛР6. Один агент или команда',title)
    p('Сравнение ReAct ЛР4 с оркестратором и тремя специализированными исполнителями. AgentDojo 0.1.35, workspace v1.2.2; Qwen3-4B-Instruct-2507 Q4_K_M, llama.cpp b12110, RTX 3060 12 ГБ. Температура 0, seed 42, контекст 16384, выход до 1024 токенов. Модель и промпт одиночного агента сохранены по SHA-256.')
    table([['Роль','Доступные инструменты','Контекст'],['Оркестратор','Три ask_*_agent','Запрос, свои сообщения, итоги исполнителей'],['Почта','7 почтовых + 2 поиска контактов','Новая история для каждого поручения'],['Календарь','7 календарных','Новая история для каждого поручения'],['Файлы','8 инструментов диска','Новая история для каждого поручения']],[90,180,230])
    p('Среда общая, истории раздельные. Общий лимит инструментов среды - 15, как у одиночного агента. У команды до 8 вызовов модели оркестратором, до 8 на поручение и до 30 за эпизод; у одиночного агента до 15. Поручения ask_* не расходуют лимит инструментов среды, но работа всех ролей расходует общий бюджет модели.',small)
    p('Прогноз и отладка',heading)
    p('До запусков: команда выиграет 1-2 многосервисные задачи, потеряет 0-3 односервисные; вызовов модели станет в 1,5-2,5 раза больше, медиана пикового входа снизится на 20-50%. На 10 отладочных задачах после общих уточнений поиска, календарных интервалов и маршрутизации контактов результат вырос с 4/10 до 5/10. Затем код и промпты зафиксированы, итоговые задачи для настройки не использовались.',small)
    p('1. Успешность и попарные переходы',heading)
    data=[['Группа','N','Один агент','Команда','Получены','Потеряны']]
    labels={'all':'Все','multi_service':'Несколько сервисов','single_service':'Один сервис'}
    for name,v in s['groups'].items():data.append([labels[name],v['n'],v['single_success'],v['multi_success'],len(v['gained']),len(v['lost'])])
    table(data,[145,30,85,80,80,80])
    p('Многосервисные задачи: 13, 15, 18, 19, 23, 25, 33. Получены: '+ids(s['groups']['multi_service']['gained'])+'. Потеряны: '+ids(s['groups']['multi_service']['lost'])+'. В группе из семи выводы даны в задачах, не в процентах.',small)
    p('Все задачи: получены '+ids(s['groups']['all']['gained'])+'; потеряны '+ids(s['groups']['all']['lost'])+'. Совместные успехи и неудачи сохранены в analysis/summary.json.',small)
    story.append(Image('analysis/architecture.png',width=500,height=150))
    p('Слева - решённые задачи по группам; в центре - медиана вызовов модели; справа - медиана наибольшего входа в одном вызове, крестом отмечен максимум.',small)
    story.append(PageBreak())
    p('2. Затраты и нагрузка на контекст',title)
    data=[['Показатель','Один агент: медиана [мин; макс]','Команда: медиана [мин; макс]','Отношение медиан']]
    labels={'model_calls':'Вызовы модели','tool_calls':'Инструменты среды','input_tokens':'Входные токены за эпизод','output_tokens':'Выходные токены за эпизод','seconds':'Время, с'}
    for key in labels:data.append([labels[key],interval(s['costs']['single'][key]),interval(s['costs']['multi'][key]),f"{s['ratios_of_medians'][key]:.2f}x"])
    table(data,[110,155,155,80])
    p('Токены суммируются по всем вызовам за эпизод, включая повторную передачу истории. Время - длительность всей работы агента, не только генерации модели. Отношение медиан отличается от отношения суммарных затрат.',small)
    p(f"Всего вызовов модели: один агент {s['costs']['single']['model_calls']['total']}, команда не менее {s['costs']['multi']['model_calls']['total']}; отношение наблюдаемых сумм {s['total_model_call_ratio']:.2f}x.",small)
    table([['Архитектура','Медиана пикового входа','Максимум пикового входа']]+[[name,s['context'][key]['median'],s['context'][key]['max']] for key,name in [('single','Один агент'),('multi','Команда')]],[130,185,185])
    p('Пиковый вход - наибольшее число prompt_tokens одного обращения к модели за эпизод. Он характеризует размер отдельного контекста; его снижение не означает снижения суммы токенов или повышения успешности.',small)
    p('Цена каждой роли за 30 задач',heading)
    table([['Роль','Вызовы модели','Входные токены','Выходные токены']]+[[role,v['model_calls'],v['input_tokens'],v['output_tokens']] for role,v in s['role_costs'].items()],[120,110,145,125])
    p(reviews['cost_example'],small)
    p('Трейс для стенда и проверки без модели',heading)
    p('Оркестратор не вызывает среду напрямую. В журнал стенда попадают только пары вызов-результат инструментов исполнителей, в фактическом порядке. Поручения остаются в собственном трейсе с ролью и delegation_id. Для составной задачи 19 важно сохранить действия календаря и последующие действия с файлами/почтой: ask_* не является функцией runtime AgentDojo и не должен подменять шаг среды.',small)
    p('Сценарные проверки: задача 33 засчитана после вызовов файлового, затем почтового исполнителя; список инструментов совпал с эталоном. Общий счётчик остановился на 15 вызовах, распределённых 7+8 между исполнителями. В журнале стенда нет ask_*. Исполнителю почты отклонён недоступный календарный инструмент. Протокол: checks.txt; код: test_multi.py.',small)
    p('Границы измерений',heading)
    p('База - 30 сохранённых эпизодов первого T=0 прогона ЛР5 от 20.11.2026; модель, промпт и лимиты одиночного агента не менялись. В ЛР6 выполнены 20 отладочных, 30 основных, 10 повторов второго опыта и один опыт вопроса 6. Основная серия прерывалась: user_task_9 учтена как неуспех без перезапуска. Полное время неизвестно (в таблице времени 29 наблюдений команды); сохранённые вызовы, токены и пиковый вход этого эпизода - нижние границы. Ошибки не исключены из доли успешности. Системное время изменений файлов не фиксировалось.',small)
    story.append(PageBreak())
    p('3. Что видит исполнитель',title)
    exp=s['experiment2'];pair=exp['pairs'];selection=read('selection.json')
    p('Повторены все 7 многосервисных задач и 3 односервисные: '+ids([x['task'] for x in selection['selected_single']])+'. Односервисные выбраны по правилу: сначала неудачи, затем убывание суммарных входных токенов. Единственное изменение - к подзадаче добавлен полный исходный запрос. Остальные промпты и бюджеты сохранены.',small)
    old={r['task']:r for r in rows('results/main.jsonl')};new={r['task']:r for r in rows('results/full_request.jsonl')};audit={r['task']:r for r in reviews['experiment2']}
    data=[['Задача','Успех: подзадача / +запрос','Пик входа: подзадача / +запрос','Потеря информации: до / после']]
    for i in selection['tasks']:data.append([i.removeprefix('user_task_'),f"{old[i]['utility']} / {new[i]['utility']}",f"{old[i]['max_input_tokens']} / {new[i]['max_input_tokens']}",f"{audit[i]['subtask_loss']} / {audit[i]['full_loss']}"])
    table(data,[50,130,160,160])
    p(f"Успех: {pair['single_success']}/10 -> {pair['multi_success']}/10; получены {ids(pair['gained'])}, потеряны {ids(pair['lost'])}. Эпизодов с потерей информации: {sum(r['subtask_loss'] for r in reviews['experiment2'])} -> {sum(r['full_loss'] for r in reviews['experiment2'])}.",small)
    p('Потеря информации - явное требование/нужный факт исчезает в поручении или итоговом сообщении исполнителя. Неверный выбор инструмента при сохранённых данных считается ошибкой исполнителя. Проверены обе версии всех 10 эпизодов; полные пояснения сохранены в analysis/reviews.json.',small)
    story.append(Image('analysis/full_request.png',width=500,height=145))
    p(reviews['experiment2_conclusion'],small)
    p('4. Почта с дополнительными инструментами календаря',heading)
    q=s['question6'];a=q['original'];b=q['expanded']
    p('Прогноз до опыта: оркестратор сможет заменить передачу сведений календарному исполнителю одним комплексным поручением почте. В отдельной конфигурации почте добавлены семь календарных инструментов; оркестратор явно уведомлён о новой возможности. Основная конфигурация не изменялась.',small)
    table([['Задача 15','Успех','Поручения','Модель / среда','Пиковый вход'],['Исходная',a['utility'],a['delegations'],f"{a['model_calls']} / {a['tool_calls']}",a['max_input_tokens']],['Почта + календарь',b['utility'],b['delegations'],f"{b['model_calls']} / {b['tool_calls']}",b['max_input_tokens']]],[125,50,75,115,135])
    p(reviews['question6'],small)
    story.append(PageBreak())
    p('5. Где теряется результат',title)
    p('Разобраны все неудачи команды на многосервисных задачах и две неудачи на односервисных. Ниже показан критический обмен каждого эпизода. Все поручения, полные итоги и вызовы инструментов сохранены в analysis/case_candidates.json и исходных трейсах; содержательная классификация выполнена с помощью Codex.',small)
    data=[['Задача','Поручение -> итог исполнителя (фрагменты)','Причина и место ошибки']]
    for case in reviews['cases']:
        h=next(h for h in case['handoffs'] if h['id']==case['critical_id'])
        quote=h['role']+': '+short(h['task'],165)+' -> '+short(h['answer'],165)
        data.append([case['task'].removeprefix('user_task_'),quote,case['cause']+'. '+case['explanation']])
    table(data,[40,275,185])
    p('Когда разделение окупается',heading)
    p(reviews['conclusion'],small)
    p('В реализации используется один и тот же экземпляр модели для всех ролей, вызовы последовательные. Выигрыш параллельного исполнения не проверялся. Успешность - оценка автоматического стенда; его ограничения из ЛР5 сохраняются. Семь многосервисных задач дают только локальное наблюдение, не универсальную оценку архитектуры.',small)
    p('Кодогенерация: Codex. Воспроизводимость: frozen.json, конфигурации, промпты, results.jsonl, baseline и traces; ноутбучный MLflow восстанавливается prepare_laptop.py без запуска модели. Источники: задание ЛР6; AgentDojo v1.2.2; Anthropic Building effective agents и How we built our multi-agent research system; OpenAI Agents SDK, Orchestrating multiple agents.',small)
    def footer(canvas,doc):
        canvas.setFont('Arial',8);canvas.drawString(45,23,'ЛР6 | Оркестратор и исполнители');canvas.drawRightString(550,23,str(doc.page))
    SimpleDocTemplate('report.pdf',pagesize=(595.28,841.89),leftMargin=45,rightMargin=45,topMargin=32,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
    import pypdfium2
    document=pypdfium2.PdfDocument('report.pdf');assert len(document)==4,len(document)
    Path('analysis/preview').mkdir(exist_ok=True)
    for i,page in enumerate(document,1):page.render(scale=1.4).to_pil().save(f'analysis/preview/{i}.png')
    print('Report ready:',len(document),'pages')
if __name__=='__main__':main()
