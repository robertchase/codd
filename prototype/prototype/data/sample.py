"""Sample data: Employee, Department, Phone, ContractorPay."""

from prototype.executor.environment import Environment
from prototype.model.relation import Relation
from prototype.model.types import Tuple_


def load_sample_data(env: Environment) -> None:
    """Load the four sample relations into the environment."""
    env.bind(
        "E",
        Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, name="Alice", salary=80000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=2, name="Bob", salary=60000, dept_id=10, role="manager"),
                    Tuple_(emp_id=3, name="Carol", salary=55000, dept_id=20, role="engineer"),
                    Tuple_(emp_id=4, name="Dave", salary=90000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=5, name="Eve", salary=45000, dept_id=20, role="engineer"),
                }
            )
        ),
    )
    env.bind(
        "D",
        Relation(
            frozenset(
                {
                    Tuple_(dept_id=10, dept_name="Engineering"),
                    Tuple_(dept_id=20, dept_name="Sales"),
                }
            )
        ),
    )
    env.bind(
        "Phone",
        Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, phone="555-1234"),
                    Tuple_(emp_id=3, phone="555-5678"),
                    Tuple_(emp_id=3, phone="555-9999"),
                }
            )
        ),
    )
    env.bind(
        "ContractorPay",
        Relation(frozenset({Tuple_(name="Frank", pay=70000)})),
    )
