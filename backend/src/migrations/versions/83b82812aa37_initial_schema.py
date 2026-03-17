from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '83b82812aa37'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('difficulties',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('coefficient_beta_bernoulli', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('skills',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('topics',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('admin', 'student', name='user_role_enum'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('subskills',
    sa.Column('skill_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('skill_id', 'name', name='uq_subskill_skill_name')
    )
    op.create_table('subtopics',
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('topic_id', 'name', name='uq_subtopic_topic_name')
    )
    op.create_table('problems',
    sa.Column('subtopic_id', sa.UUID(), nullable=False),
    sa.Column('difficulty_id', sa.UUID(), nullable=False),
    sa.Column('condition_latex', sa.Text(), nullable=False),
    sa.Column('solution_latex', sa.Text(), nullable=False),
    sa.Column('condition_image_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('solution_image_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['difficulty_id'], ['difficulties.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['subtopic_id'], ['subtopics.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('subskill_prerequisites',
    sa.Column('subskill_id', sa.UUID(), nullable=False),
    sa.Column('prerequisite_subskill_id', sa.UUID(), nullable=False),
    sa.Column('mastery_weight', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('mastery_weight >= 0 AND mastery_weight <= 1', name='ck_subskill_weight'),
    sa.ForeignKeyConstraint(['prerequisite_subskill_id'], ['subskills.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subskill_id'], ['subskills.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('subskill_id', 'prerequisite_subskill_id', name='uq_subskill_prerequisite_pair')
    )
    op.create_table('subtopic_prerequisites',
    sa.Column('subtopic_id', sa.UUID(), nullable=False),
    sa.Column('prerequisite_subtopic_id', sa.UUID(), nullable=False),
    sa.Column('mastery_weight', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('mastery_weight >= 0 AND mastery_weight <= 1', name='ck_subtopic_weight'),
    sa.ForeignKeyConstraint(['prerequisite_subtopic_id'], ['subtopics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subtopic_id'], ['subtopics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('subtopic_id', 'prerequisite_subtopic_id', name='uq_subtopic_prerequisite_pair')
    )
    op.create_table('problem_answer_options',
    sa.Column('problem_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('text_latex', sa.Text(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('position >= 1 AND position <= 8', name='ck_answer_option_position'),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('problem_id', 'position', name='uq_problem_answer_option_position')
    )
    op.create_index('uq_problem_correct_answer', 'problem_answer_options', ['problem_id'], unique=True, postgresql_where=sa.text('is_correct = true'))
    op.create_table('problem_subskills',
    sa.Column('problem_id', sa.UUID(), nullable=False),
    sa.Column('subskill_id', sa.UUID(), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.CheckConstraint('weight >= 0 AND weight <= 1', name='ck_problem_subskill_weight'),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subskill_id'], ['subskills.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('problem_id', 'subskill_id', name='pk_problem_subskills')
    )
    op.create_table('user_failed_problems',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('problem_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'problem_id', name='pk_user_failed_problem')
    )
    op.create_table('user_solved_problems',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('problem_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'problem_id', name='pk_user_solved_problem')
    )


def downgrade() -> None:
    op.drop_table('user_solved_problems')
    op.drop_table('user_failed_problems')
    op.drop_table('problem_subskills')
    op.drop_index('uq_problem_correct_answer', table_name='problem_answer_options', postgresql_where=sa.text('is_correct = true'))
    op.drop_table('problem_answer_options')
    op.drop_table('subtopic_prerequisites')
    op.drop_table('subskill_prerequisites')
    op.drop_table('problems')
    op.drop_table('subtopics')
    op.drop_table('subskills')
    op.drop_table('users')
    op.drop_table('topics')
    op.drop_table('skills')
    op.drop_table('difficulties')
