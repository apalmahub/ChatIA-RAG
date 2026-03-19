from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from database import get_db
from models import Project
from schemas import Project as ProjectSchema, ProjectCreate
from auth import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=ProjectSchema)
async def create_project(
    project: ProjectCreate,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new project"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only administrators can create projects")
    try:
        # Check for duplicate name for this user
        existing = await db.execute(
            select(Project).where(
                Project.user_id == current_user.id,
                Project.name == project.name
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail=f"Ya existe un proyecto con el nombre '{project.name}'")

        db_project = Project(
            user_id=current_user.id,
            name=project.name,
            description=project.description
        )
        db.add(db_project)
        await db.commit()
        await db.refresh(db_project)
        
        logger.info(f"Project created: {project.name} by user {current_user.email}")
        return db_project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Project creation failed")

@router.get("/", response_model=List[ProjectSchema])
async def get_projects(
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get accessible projects"""
    try:
        # For simplicity in this requirement, todos ven todos los proyectos
        # pero solo el admin puede editarlos/crearlos
        result = await db.execute(
            select(Project)
            .offset(skip)
            .limit(limit)
            .order_by(Project.created_at.desc())
        )
        projects = result.scalars().all()
        
        return projects
    except Exception as e:
        logger.error(f"Failed to get projects: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve projects")

@router.get("/{project_id}", response_model=ProjectSchema)
async def get_project(
    project_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific project"""
    try:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
        )
        project = result.scalars().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve project")

@router.put("/{project_id}", response_model=ProjectSchema)
async def update_project(
    project_id: str,
    project_update: ProjectCreate,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a project"""
    try:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
        )
        project = result.scalars().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if not current_user.is_superuser and project.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")
            
        project.name = project_update.name
        project.description = project_update.description
        
        await db.commit()
        await db.refresh(project)
        
        logger.info(f"Project updated: {project.name} by user {current_user.email}")
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Update failed")

@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a project"""
    try:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
        )
        project = result.scalars().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Only administrators can delete projects")
            
        await db.delete(project)
        await db.commit()
        
        logger.info(f"Project deleted: {project_id} by user {current_user.email}")
        return {"message": "Project deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Delete failed")
