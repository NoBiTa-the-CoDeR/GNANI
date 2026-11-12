import { defineConfig } from 'jsrepo';
import stripTypes from '@jsrepo/transform-javascript';

export default defineConfig({
    // configure where stuff comes from here
    registries: ['https://reactbits.dev/r'],
    // configure where stuff goes here
    paths: { component: './src/components/reactbits',
		file: './src/components/reactbits' },
	transforms: [stripTypes()]
});