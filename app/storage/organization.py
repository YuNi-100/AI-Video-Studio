"""Persisted folders and independent library/editing references."""
from copy import deepcopy
from app.core.project import validate_display_name


def folders(value):
    if not isinstance(value,list) or len(value)>1000:raise ValueError('폴더 목록이 올바르지 않습니다.')
    result=[];ids=set()
    for row in value:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not 0<len(row['id'])<=64 or row['id'] in ids:raise ValueError('폴더 ID가 올바르지 않습니다.')
        ids.add(row['id']);result.append(dict(id=row['id'],name=validate_display_name(row.get('name')),parent=row.get('parent')))
    parents={r['id']:r['parent'] for r in result}
    for row in result:
        chain=set();node=row['id']
        while node is not None:
            if node in chain or node not in parents:raise ValueError('폴더의 상위 경로가 올바르지 않습니다.')
            chain.add(node);node=parents[node]
    return result


def references(value,folder_ids,paths,resolve=lambda p:p):
    if not isinstance(value,list) or len(value)>10000:raise ValueError('자료 목록이 올바르지 않습니다.')
    result=[];ids=set()
    for row in value:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not 0<len(row['id'])<=64 or row['id'] in ids:raise ValueError('자료 ID가 올바르지 않습니다.')
        source=resolve(row.get('source'))
        if source not in paths or row.get('folder') not in folder_ids|{None}:raise ValueError('자료의 원본 또는 폴더가 없습니다.')
        ids.add(row['id']);result.append(dict(id=row['id'],source=source,name=validate_display_name(row.get('name')),folder=row.get('folder')))
    return result


def load_organization(project,data,resolve):
    project.library_folders=folders(data.get('library_folders',[]))
    project.edit_folders=folders(data.get('edit_folders',[]))
    library=data.get('library_items')
    project.library_items=None if library is None else references(library,{r['id'] for r in project.library_folders},set(project.media_paths),resolve)
    project.edit_assets=references(data.get('edit_assets',[]),{r['id'] for r in project.edit_folders},set(project.media_paths),resolve)
    locations=data.get('edit_locations',{})
    if not isinstance(locations,dict) or len(locations)>1000:raise ValueError('편집본 폴더 정보가 올바르지 않습니다.')
    seqids={s['id'] for s in project.edit_sequences};folderids={r['id'] for r in project.edit_folders}
    if any(key not in seqids or folder not in folderids|{None} for key,folder in locations.items()):raise ValueError('편집본 폴더 연결이 올바르지 않습니다.')
    project.edit_locations=deepcopy(locations)


def dump_organization(project,portable):
    data=dict(library_folders=project.library_folders,edit_folders=project.edit_folders,library_items=project.library_items,edit_assets=project.edit_assets,edit_locations=project.edit_locations)
    # Validate using exactly the same rules before writing.
    from copy import copy
    check=copy(project);load_organization(check,data,lambda p:p)
    result=deepcopy(data)
    for key in ('library_items','edit_assets'):
        if result[key] is not None:
            for row in result[key]:row['source']=portable(row['source'])
    return result
