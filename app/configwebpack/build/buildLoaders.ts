import webpack from 'webpack';
import { BuildOptions } from './types/config';
import { buildCssLoader } from './loaders/buildCssLoader';
import { buildBabelLoader } from './loaders/buildBabelLoader';

// Todo el TypeScript y el JSX pasan por Babel (buildBabelLoader), no por
// ts-loader: el chequeo de tipos vive en `npm run typecheck`, separado del build.
export function buildLoaders(options: BuildOptions): webpack.RuleSetRule[] {
    const urlLoader = {
        test: /\.(jpg|png|jpeg)$/,
        use: {
            loader: 'url-loader',
        },
    };

    const codeBabelLoader = buildBabelLoader({ ...options, isTsx: false });
    const tsxCodeBabelLoader = buildBabelLoader({ ...options, isTsx: true });
    const cssLoader = buildCssLoader(options);

    return [
        codeBabelLoader,
        tsxCodeBabelLoader,
        cssLoader,
        urlLoader,
    ];
}
