import asyncio
from time import perf_counter_ns

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.settings import get_settings


async def config_resources() -> EveArgusResources:
    """Configure and return an instance of EveArgusResources."""
    settings = get_settings()
    print(f"Using settings: {settings}")
    resource_manager = EveArgusResources(settings=settings)
    return resource_manager


async def prove_static_data_loader(resource_manager: EveArgusResources):
    """Prove the static data loader by loading and printing ESD datasets."""
    async with resource_manager as resources:
        esd_loader = EsdDatasetsLoader(resources.sd_query_manager)
        # Measure the time taken to load each dataset and print the results

        start_time = perf_counter_ns()
        blueprints = esd_loader.blueprints()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load blueprints: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(blueprints)} blueprints.")

        start_time = perf_counter_ns()
        type_materials = esd_loader.type_materials()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load type materials: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(type_materials)} type materials.")

        start_time = perf_counter_ns()
        types_published: bool | None = (
            True  # Change this to False or None to test other cases
        )
        types = esd_loader.types(published=types_published)
        end_time = perf_counter_ns()
        print(
            f"Time taken to load types: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(types)} types. Published filter: {types_published}")

        start_time = perf_counter_ns()
        meta_groups = esd_loader.meta_groups()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load meta groups: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(meta_groups)} meta groups.")

        start_time = perf_counter_ns()
        categories = esd_loader.categories()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load categories: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(categories)} categories.")

        start_time = perf_counter_ns()
        groups = esd_loader.groups()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load groups: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(groups)} groups.")


if __name__ == "__main__":
    # measure the time take in seconds to acuire the manager, and the total time to load the datasets
    start_time = perf_counter_ns()
    resources = asyncio.run(config_resources())
    end_time = perf_counter_ns()
    print(
        f"Time taken to configure resources: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    start_time = perf_counter_ns()
    asyncio.run(prove_static_data_loader(resources))
    end_time = perf_counter_ns()
    print(
        f"Total time taken to load all datasets: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
